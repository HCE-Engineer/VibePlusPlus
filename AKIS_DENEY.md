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

## 2. Akış v0 dil şartnamesi

Bu bölüm aynı zamanda deneyde modele verilecek şartnamedir (`spec/AKIS_SPEC.md` olarak ayrıca kaydet, ikisi aynı kalsın).

### Dosya
- Uzantı `.aks`, UTF-8. Girinti 2 boşluk, tab yasak.
- Üst düzey öğeler: `use`, `type`, `fn`. Yorum: `#`.

### Tipler
```
int  float  str  bool  none  any(sadece use py içinde)
[T]          liste
{K: V}       sözlük
(A, B)       demet; elemanlara .0 .1 ile erişilir
T?           opsiyonel: değer ya da none
T!           hata dönebilir
type Part = {name: str, weight: float}     # kayıt tipi
Part(name: "mil", weight: 2.5)             # kayıt oluşturma, isimli alanlar zorunlu
```

### Fonksiyon
```
fn name(a: T, b: U) -> R !fs !io
  gövde
```
- Gövdenin son satırındaki ifade dönüş değeridir. Erken dönüş için `return expr`.
- Efektler: `!fs` (dosya), `!net` (ağ), `!io` (konsol), `!time` (saat), `!rand` (rastgele). Efekt yazılmamış fonksiyon saftır.
- **Kural E1:** `f`, `g`'yi çağırıyorsa `g`'nin tüm efektleri `f`'nin imzasında olmalı.
- **Kural E2:** `?` operatörü sadece dönüş tipi `T!` olan fonksiyonda kullanılabilir.
- **Kural N1:** Blok iç içeliği en fazla 2 seviye (fonksiyon gövdesi sayılmaz). Fazlası derleme hatası.
- **Kural N2:** 3 veya daha fazla parametreli fonksiyon çağrılarında isimli argüman zorunlu: `clamp(value: x, low: 0, high: 255)`.

### Bağlama
```
let x = expr              # değiştirilemez
let x: [int] = []         # tip yazılabilir
var total = 0             # değiştirilebilir
total = total + 1
```

### Akış (pipeline)
```
expr | aşama | aşama
```
Aşamalar:
| Aşama | Anlamı |
|---|---|
| `f` | `f(önceki)` |
| `f(a, b)` | `f(önceki, a, b)` |
| `where P` | P doğru olanları tut |
| `map E` | her elemanı E'ye dönüştür |
| `sort_by K` / `sort_by K desc` | K anahtarına göre sırala (kararlı) |
| `count_by K` | `[(anahtar, adet)]`, ilk görülme sırasıyla |
| `group_by K` | `{anahtar: [elemanlar]}` |
| `take n`, `skip n` | ilk n / ilk n hariç |
| `sum`, `min`, `max`, `len`, `unique`, `flatten`, `sort` | adı gibi; `min`/`max` boş listede hata |
| `first` | `T?` döner |

- Aşama içinde `it` mevcut eleman, `.alan` kısaltması `it.alan` demek, `.0` demetin ilk elemanı.
- Bir aşamanın ifadesi bir sonraki üst düzey `|` işaretine kadar uzanır.
- Çok satırlı akışta devam satırı 4 boşluk girinti ve `|` ile başlar.
- `|` sadece akış operatörüdür; bit düzeyi işlem yok.

### Hata ve opsiyonel
```
read_text(path)?          # hata ise fonksiyondan aynı hatayla çık
fail("negatif kütle")     # hata üret
to_int(s) ?? 0            # hata veya none ise varsayılan
```

### Kontrol
```
if c:
  ...
elif c:
  ...
else:
  ...
let y = if c then a else b     # tek satır ifade
for x in xs:
  ...
while c:
  ...
```

### Operatörler ve değerler
`+ - * / // % ** == != < <= > >= and or not in`. Metin `"..."`, içinde `{x}` ile değer yerleştirme. Liste `[1, 2]`, sözlük `{"a": 1}`, indeksleme `xs[i]` (aralık dışı çalışma zamanı hatası).

### Python ile birlikte çalışma
```
use py math.sqrt as sqrt: (float) -> float
use py json.loads as parse_json: (str) -> any!
```
İçe aktarılan her Python fonksiyonunun tipi ve efektleri yazılmak zorunda.

### Yerleşik fonksiyonlar
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
parse_csv(text: str) -> [{str: str}]    # ilk satır başlık
abs, round(x, n), str(x), int(x), float(x)
```

### Derleyici hata çıktısı
Her hata tek satır JSON:
```
{"code": "E-EFFECT-01", "at": "sol.aks:4:3", "msg": "pure fn 'summary' calls 'read_text' (effect !fs)", "fix": "add !fs to 'summary' signature"}
```
Kodlar: `E-SYNTAX-*`, `E-TYPE-*`, `E-EFFECT-*`, `E-NEST-01`, `E-NAMEDARG-01`, `E-QMARK-01`.

### Örnek programlar
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
