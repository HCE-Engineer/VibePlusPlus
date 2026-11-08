# Akış Deneyi — AI-native programlama dili testi

Bu repo bir deney. Amaç: **bir LLM'in token üretim mekanizmasına göre tasarlanmış bir programlama dili (Akış), aynı işi Python'dan daha az token ve daha az hatayla yazdırabiliyor mu?** sorusunu ölçmek.

İnsan okunurluğu hedef DEĞİL. Tek hedef: AI'ın rahat yazması ve okuması, toplam token maliyetinin düşmesi.

Proje sahibi: H. Her "DUR" noktasında çalışmayı durdur ve H'ye rapor ver.

---

## 1. Hipotez ve gerekçe

Tasarım şu gözlemlere dayanıyor (bunlar doğrulanmamış varsayımlar, deney bunları test ediyor):

1. **Kısa sembol ≠ az token.** Nadir semboller (APL tarzı) tokenizer'da birden çok token tutar. Yaygın İngilizce kelimeler ve Python/Rust noktalaması tek token. Akış bu yüzden tanıdık kelime ve noktalama kullanır.
2. **Model soldan sağa, geri dönmeden üretir.** `sort(count(filter(x)))` en dıştaki işlemi önce seçmeyi gerektirir. `x | filter | count | sort` üretim sırasıyla aynıdır.
3. **Kapanış sayma hata kaynağıdır.** `)))}` dizileri yok; bloklar girintiyle biter.
4. **Toplam maliyeti sözdizimi değil, başarısız denemeler belirler.** Bir düzeltme döngüsü yüzlerce token yer. Asıl metrik: başarıya kadar harcanan toplam çıktı token'ı.
5. **Tanıdıklık en büyük avantaj.** Akış'ın her parçası modelin çok gördüğü bir dilden alınır: `|` Unix'ten, `?` Rust'tan, `.alan` jq/Kotlin'den, efekt işaretleri Koka'dan. Yeni olan sadece birleşim.

Bilinen dezavantaj: model Akış'ı eğitimde hiç görmedi. Şartname her istemde bağlama verilir. Bu, Akış koluna karşı bir handikap; sonuç pozitif çıkarsa bu handikaba rağmen çıkmış olur.

---

## 2. Akış v0.2 dil şartnamesi

Bu bölüm aynı zamanda deneyde modele verilecek şartnamedir (`spec/AKIS_SPEC.md` olarak ayrıca kaydet, ikisi aynı kalsın. v0.2'den itibaren modele giden metin İngilizce).

### File
- Extension `.aks`, UTF-8. Indent 2 spaces, tabs are forbidden.
- Top-level items: `use`, `type`, `fn`. Comment: `#`.

### Types
```
int  float  str  bool  none  any(only inside use py)
[T]          list
{K: V}       dict
(A, B)       tuple; elements are accessed with .0 .1
T?           optional: a value or none
T!           may return an error
type Part = {name: str, weight: float}     # record type
Part(name: "mil", weight: 2.5)             # record construction, named fields required
```

### Functions
```
fn name(a: T, b: U) -> R !fs !io
  body
```
- The expression on the last line of the body is the return value. Early return: `return expr`.
- Effects: `!fs` (files), `!net` (network), `!io` (console), `!time` (clock), `!rand` (random). A function with no effects written is pure.
- **Rule E1:** if `f` calls `g`, all effects of `g` must be in `f`'s signature.
- **Rule E2:** the `?` operator may only be used in a function whose return type is `T!`.
- **Rule N1:** block nesting is at most 3 levels (the function body and a single-statement block on the same line do not count). More is a compile error.
- **Rule N2:** calls to your own functions with 3 or more parameters must use named arguments: `clamp(value: x, low: 0, high: 255)`. Builtins are exempt.
- A call can be written in three equivalent forms: `f(x, a)`, `x.f(a)`, `x | f(a)`.

### Bindings
```
let x = expr              # immutable
let x: [int] = []         # type may be written
var total = 0             # mutable
total = total + 1
total += 1                # += -= *= /= //= %=
let a, b = pair           # tuple unpacking
a, b = b, a
xs[i] = v                 # element assignment on a var; d[k] = v, p.field = v
```

### Pipelines
```
expr | stage | stage
```
Stages:
| Stage | Meaning |
|---|---|
| `f` | `f(previous)` |
| `f(a, b)` | `f(previous, a, b)` |
| `where P` | keep elements where P is true |
| `map E` | transform each element to E |
| `sort_by K` / `sort_by K desc` | sort by key K (stable) |
| `sort` / `sort desc` | sort by value |
| `max_by K`, `min_by K` | element with the largest / smallest K; error on an empty list |
| `count_by K` | `[(key, count)]`, in first-seen order |
| `group_by K` | `{key: [elements]}` |
| `take n`, `skip n` | first n / all but the first n |
| `sum`, `min`, `max`, `avg`, `len`, `unique`, `flatten`, `reverse` | as named; `min`/`max`/`avg` error on an empty list |
| `first` | returns `T?` |

- Inside a stage `it` is the current element, `.field` is short for `it.field`, `.0` is the first element of a tuple.
- A stage's expression extends to the next top-level `|`.
- In a multi-line pipeline, a continuation line is indented 4 spaces and starts with `|`.
- `|` is only the pipeline operator; there are no bitwise operations.
- A pipeline over a dict yields `(key, value)` tuples: `d | sort_by .1 desc | map .0`.
- If an expression containing a pipeline is part of another expression, parenthesise it: `if (xs | len) > 3:`.

### Errors and optionals
```
read_text(path)?          # on error, return from the function with the same error
fail("negative mass")      # raise an error
to_int(s) ?? 0            # default if error or none
d[k] ?? 0                 # a missing key / out-of-range index is also an error
```

### Control flow
```
if c:
  ...
elif c:
  ...
else:
  ...
let y = if c then a else b     # single-line expression
for x in xs:
  ...
for i, x in enumerate(xs):
  ...
while c:
  ...
if x < 0: return 0             # a single-statement block may be on the same line
```
`break` and `continue` are used inside loops. When `if/elif/else` is the last line, the last expression of each branch is the return value.

### Operators and values
`+ - * / // % ** == != < <= > >= and or not in`. `true`, `false`, `none`. Strings `"..."`, with `{x}` or `{x:.2f}` interpolation inside. List `[1, 2]`, dict `{"a": 1}`, indexing `xs[i]`, `xs[-1]`, slice `xs[a:b]` (lists and strings). List comprehensions `[E for x in xs if P]` are also valid.

### Python interop
```
use py math.sqrt as sqrt: (float) -> float
use py json.loads as parse_json: (str) -> any!
use py os.path.exists as exists: (str) -> bool !fs
```
Every imported Python function must have its type and effects written.
Only these modules are allowed; functions from the module must declare the listed effect:
- pure: `math cmath statistics json re string itertools functools operator collections heapq bisect fractions decimal textwrap unicodedata difflib hashlib base64 binascii struct copy colorsys html csv fnmatch urllib.parse`
- `!fs`: `os os.path pathlib shutil glob tempfile`
- `!net`: `urllib.request http.client socket ssl`
- `!time`: `time datetime`
- `!rand`: `random secrets uuid`

Process and interpreter functions (`os.system`, `os.popen`, `exec*`, `spawn*`, `fork`, `kill`, `eval`, ...) are never allowed.

### Builtin functions
```
read_text(path: str) -> str!            !fs
write_text(path: str, text: str) -> none!   !fs
print(x: any) -> none                   !io
now() -> float                          !time
random() -> float                       !rand
lines(s: str) -> [str]
split(s: str, sep: str) -> [str]
strip(s: str) -> str
join(xs: [str], sep: str) -> str
to_int(s: str) -> int!
to_float(s: str) -> float!
parse_csv(text: str) -> [{str: str}]    # first line is the header
fail(msg: str)                          # only in a function returning T!
```
Others (all pure):
```
number: abs round(x, n) min max sqrt floor ceil log exp int(x) float(x) str(x)
list:   len sum avg unique flatten reverse sort first last take(xs, n) skip(xs, n)
        range(n) range(a, b) range(a, b, step) enumerate(xs) zip(a, b) any(xs) all(xs)
        find(xs, x) count(xs, x)            # find: -1 if absent
        append(xs, x) pop(xs)               # modify in place, xs must be a var
dict:   keys values items get(d, k) get(d, k, default) dict(pairs)
string: split(s) split(s, sep) join(xs, sep) strip lstrip rstrip upper lower
        replace(s, old, new) starts_with ends_with chars is_digit is_alpha is_space
        ord chr find(s, sub) count(s, sub)
```
`first`, `last`, `get(d, k)` → `T?`. `int(s)`, `float(s)` raise an error on invalid text (catch with `?? 0`).

### Compiler error output
Each error is one line of JSON:
```
{"code": "E-EFFECT-01", "at": "sol.aks:4:3", "msg": "pure fn 'summary' calls 'read_text' (effect !fs)", "fix": "add !fs to 'summary' signature"}
```
Codes: `E-SYNTAX-*`, `E-TYPE-*`, `E-EFFECT-*`, `E-NEST-01`, `E-NAMEDARG-01`, `E-QMARK-01`.

### Example programs
```
type Part = {name: str, weight: float}

fn heavy_parts(parts: [Part], limit: float) -> [Part]
  parts | where .weight > limit
```
```
fn failing_machines(path: str) -> [(str, int)]! !fs
  read_text(path)? | parse_csv | where it["status"] == "fail"
    | count_by it["machine"] | sort_by .1 desc
```
```
fn running_max(xs: [int]) -> [int]
  var best = xs | first ?? 0
  var out: [int] = []
  for x in xs:
    if x > best:
      best = x
    out = out + [best]
  out
```
```
fn total_mass(path: str) -> float! !fs
  let text = read_text(path)?
  text | lines | where strip(it) != "" | map to_float(it) ?? 0.0 | sum
```

---

## 3. Uygulama: transpiler

- Python 3.11, parser için **Lark**. Akış → Python 3.11 kaynak kodu.
- `runtime/akis_rt.py`: akış aşamalarının Python karşılıkları.
- **Hata semantiği (iki kolda aynı test çalışsın diye):** `fail(msg)` Python'da `AksError(ValueError)` fırlatır. `?` hatayı yukarı iletir. `??` `AksError` ve `None` yakalar. Testler hata durumlarını `pytest.raises(ValueError)` ile kontrol eder; Python kolu da `ValueError` fırlatır.
- Tip ve efekt denetimi statik yapılır; denetimden geçmeyen kod Python'a çevrilmez.
- Fonksiyon isimleri Python'a aynen geçer, böylece aynı test dosyası iki kolun çıktısını da test eder.
- CLI: `akis check sol.aks` (JSON hatalar), `akis build sol.aks -o sol.py`.
- Transpiler'ın kendi birim testleri `akis/tests/` altında; bölüm 2'deki örnek programların hepsi derlenip doğru çalışmalı.

**DUR 1:** Transpiler ve örnekler çalışınca H'ye göster.

---

## 4. Görev seti

- **35 görev:** 5 geliştirme (dev) + 30 test. Dev görevleri sadece şartname/harness ayarı için. Test görevleri ana deneyde bir kez kullanılır.
- 30 test görevi üç katmanda, her katmanda 10:
  - **K1 Veri dönüşümü** (filtrele, grupla, say, sırala). Akış lehine olması beklenir.
  - **K2 Algoritma ve durum** (döngü, durum makinesi, arama, iki işaretçi, basit DP). Akış lehine olmaması beklenir; bu katman yanlılığı dengelemek için var.
  - **K3 Mühendislik ve efektli iş** (dosya okuma/yazma, birim hesapları, hata girdisi işleme, birden çok fonksiyon).
- Her görev `tasks/<id>/` altında:
  - `task.md`: İngilizce, dil bağımsız açıklama (iki kolda birebir aynı metin).
  - `signature.py` ve `signature.aks`: aynı isim ve tiplerle imza.
  - `test_hidden.py`: en az 6 test, en az 1 kenar durum, gerekiyorsa hata durumu.
  - `reference.py`: testleri doğrulamak için Python çözümü.
- Görevler zorluk olarak gerçekçi olsun: çözüm 5-40 satır.
- **Kilit:** Testler bitince `tasks/LOCK.sha256` dosyasına tüm `task.md` ve `test_hidden.py` dosyalarının hash'ini yaz. Ana koşudan sonra hash değişmişse deney geçersiz.
- **Yasak:** Test görevleri için Akış çözümü yazma, görmeye çalışma, şartnameyi test görevlerine göre ayarlama.

**DUR 2:** Görev listesini (başlık + katman + 1 cümle) H'ye göster, onay al.

---

## 5. Harness

Denek, bu oturumdaki Claude Code DEĞİL. Denek, temiz bağlamda API üzerinden çağrılan modeldir.

- `harness/run.py`, Anthropic Python SDK, API anahtarı `ANTHROPIC_API_KEY` ortam değişkeninden.
- `harness/config.yaml`:
  ```
  models: [claude-sonnet-5-5, claude-haiku-5-5]   # ana model: ilki
  runs_per_task: 5
  max_repairs: 3
  max_tokens: 4000
  ```
  Model isimlerini ve token sayma endpoint'ini kullanmadan önce güncel API dokümantasyonundan doğrula: https://docs.claude.com/en/api/overview
- Her deneme bağımsız, sıfır geçmişli bir istek. Sıcaklık varsayılan.

### İstem şablonları
Python kolu:
```
Task:
{task.md}

Implement this in Python 3.11:
{signature.py}

Output only one code block containing the complete solution. No explanation.
```
Akış kolu:
```
<spec>
{AKIS_SPEC.md}
</spec>

Task:
{task.md}

Implement this in Akış, following the spec exactly:
{signature.aks}

Output only one code block containing the complete solution. No explanation.
```
Düzeltme istemi (iki kolda aynı yapı):
```
Your previous solution:
{kod}

It failed with:
{hata}

Output only one code block with the complete corrected solution.
```
- Hata metni: derleme hatalarının tamamı; test hatasında ilk başarısız testin adı ve assertion farkı.
- Kod bloğu çıkarılamazsa sözdizimi hatası sayılır.

### Kaydedilecekler (`results/raw/*.jsonl`, her deneme bir satır)
model, kol, görev, katman, koşu no, deneme no, istem, ham yanıt, çıkarılan kod, `usage.input_tokens`, `usage.output_tokens`, kod token sayısı (sadece çıkarılan kodun token sayısı, token sayma endpoint'iyle), sonuç (geçti / sözdizimi / tip-efekt / test), hata metni, süre.

**DUR 3:** Dev görevlerde 2 koşuluk pilot yap. Harness'in uçtan uca çalıştığını göster, ana koşunun tahmini maliyetini hesapla, onay al. Şartnamede değişiklik sadece bu aşamada ve sadece dev sonuçlarına göre yapılabilir; yapılan her değişikliği `spec/CHANGELOG.md`'ye yaz. Pilottan sonra şartname dondurulur.

---

## 6. Metrikler

Her görev için 5 koşunun ortalaması alınır, karşılaştırma görev bazında eşleştirilmiş yapılır.

| Metrik | Tanım |
|---|---|
| **pass@1** | İlk denemede tüm testleri geçen koşu oranı |
| **pass@final** | En fazla 3 düzeltmeyle geçen koşu oranı |
| **KT** | İlk denemedeki kod token sayısı (sadece kod) |
| **TT** | Başarıya kadar toplam çıktı token'ı (bütün denemeler). Başarısız koşuda tüm denemelerin toplamı alınır. |
| **DD** | Ortalama düzeltme döngüsü sayısı |
| **Hata dağılımı** | Sözdizimi / tip-efekt / test hatası oranları |
| **Girdi yükü** | Akış kolunun şartname yüzünden fazladan harcadığı girdi token'ı (ayrı raporlanır, başarı ölçütüne dahil değil) |

İstatistik: Oran ve oran farkları için görevler üzerinden bootstrap ile %95 güven aralığı (10.000 örnek). Token karşılaştırmaları için Akış/Python oranının medyanı ve güven aralığı.

---

## 7. Başarı ve başarısızlık şartları

Bu eşikler deney başlamadan sabitlendi. Sonuç görüldükten sonra değiştirilemez. Değerlendirme ana model ve 30 test görevinin tamamı üzerinden yapılır; katman sonuçları ayrıca raporlanır ama karar tümüne göre verilir.

### BAŞARI (üçü birden sağlanmalı)
- **S1 Sıkışma:** KT oranı (Akış/Python) medyanı **≤ 0,80**. Yani kod en az %20 daha az token.
- **S2 Doğruluk kaybı yok:** pass@1(Akış) **≥** pass@1(Python) **− 5 puan**.
- **S3 Asıl hedef:** TT oranı (Akış/Python) medyanı **≤ 0,85**. Yani başarıya kadar toplam çıktı en az %15 daha az.

### BAŞARISIZLIK (herhangi biri yeterli)
- **F1:** pass@1(Akış) < pass@1(Python) − 15 puan.
- **F2:** TT oranı medyanı ≥ 1,00. Yani hatalar sözdizimi kazancını tamamen yiyor.
- **F3:** Akış kolundaki başarısız ilk denemelerin **%25'inden fazlası sözdizimi hatası**. Bu, dilin bağlam içinde öğrenilemediğini gösterir.

### KISMİ / BELİRSİZ
- Ne başarı ne başarısızlık şartları sağlanıyorsa: **kısmi**. Hata dağılımı analiz edilir, şartname v0.2 için en fazla 2 iterasyon yapılabilir; her iterasyon **yeni** 30 görevlik bir setle test edilir (eski set artık dev seti sayılır).
- Bir ölçütün güven aralığı eşiğin iki tarafına da uzanıyorsa o ölçüt **belirsiz** sayılır ve raporda öyle yazılır. Belirsiz ölçüt başarı sayılmaz.

### Beklenen örüntü (yorum için, karar için değil)
K1'de Akış'ın belirgin kazanması, K2'de başa baş veya kaybetmesi beklenir. K2'de büyük kayıp, dilin döngü/durum kısmının zayıf olduğunu gösterir.

---

## 8. Rapor

`results/REPORT.md`:
1. Tek cümlelik sonuç: BAŞARI / BAŞARISIZLIK / KISMİ, hangi ölçütlerle.
2. Ana tablo: her metrik, iki kol, fark, güven aralığı.
3. Katman bazında tablo (K1, K2, K3).
4. Hata dağılımı ve en sık 5 Akış hatası, örnek kodlarla.
5. Her koldan 3 temsilî çözüm yan yana.
6. İkinci model (haiku) sonuçları ayrı bölümde.
7. Sınırlamalar: şartname bağlamda verildi, görevleri deneyi bilen bir model yazdı, tek tokenizer, tek model ailesi.

**DUR 4:** Raporu H'ye sun.

---

## 9. Çalışma kuralları

- Klasör yapısı: `akis/` (transpiler), `runtime/`, `spec/`, `tasks/`, `harness/`, `results/`.
- Her fazın sonunda git commit.
- API maliyeti DUR 3'te onaylanan bütçeyi aşacaksa dur ve sor.
- Başarı şartlarını, görevleri veya testleri kilitten sonra değiştirme. Bir hata bulursan düzeltme, H'ye bildir; H karar verir.
- Olumsuz sonuç da sonuçtur. Sonucu güzel göstermek için hiçbir şeyi ayarlama.
