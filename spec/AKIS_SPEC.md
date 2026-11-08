# Akış v0.1 dil şartnamesi

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
- **Kural N1:** Blok iç içeliği en fazla 3 seviye (fonksiyon gövdesi ve aynı satırdaki tek deyimli blok sayılmaz). Fazlası derleme hatası.
- **Kural N2:** 3 veya daha fazla parametreli kendi fonksiyonlarına yapılan çağrılarda isimli argüman zorunlu: `clamp(value: x, low: 0, high: 255)`. Yerleşik fonksiyonlar muaf.
- Çağrı üç biçimde yazılabilir, üçü aynıdır: `f(x, a)`, `x.f(a)`, `x | f(a)`.

### Bağlama
```
let x = expr              # değiştirilemez
let x: [int] = []         # tip yazılabilir
var total = 0             # değiştirilebilir
total = total + 1
total += 1                # += -= *= /= //= %=
let a, b = pair           # demet açma
a, b = b, a
xs[i] = v                 # var üzerinde eleman ataması; d[k] = v, p.alan = v
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
| `sort` / `sort desc` | değere göre sırala |
| `max_by K`, `min_by K` | K'si en büyük / en küçük eleman; boş listede hata |
| `count_by K` | `[(anahtar, adet)]`, ilk görülme sırasıyla |
| `group_by K` | `{anahtar: [elemanlar]}` |
| `take n`, `skip n` | ilk n / ilk n hariç |
| `sum`, `min`, `max`, `avg`, `len`, `unique`, `flatten`, `reverse` | adı gibi; `min`/`max`/`avg` boş listede hata |
| `first` | `T?` döner |

- Aşama içinde `it` mevcut eleman, `.alan` kısaltması `it.alan` demek, `.0` demetin ilk elemanı.
- Bir aşamanın ifadesi bir sonraki üst düzey `|` işaretine kadar uzanır.
- Çok satırlı akışta devam satırı 4 boşluk girinti ve `|` ile başlar.
- `|` sadece akış operatörüdür; bit düzeyi işlem yok.
- Sözlük üzerinde akış `(anahtar, değer)` demetleri verir: `d | sort_by .1 desc | map .0`.
- Akış içeren bir ifade başka bir ifadenin parçasıysa parantez: `if (xs | len) > 3:`.

### Hata ve opsiyonel
```
read_text(path)?          # hata ise fonksiyondan aynı hatayla çık
fail("negatif kütle")     # hata üret
to_int(s) ?? 0            # hata veya none ise varsayılan
d[k] ?? 0                 # olmayan anahtar / aralık dışı indeks de hatadır
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
for i, x in enumerate(xs):
  ...
while c:
  ...
if x < 0: return 0             # tek deyimli blok aynı satırda olabilir
```
`break`, `continue` döngü içinde kullanılır. Son satırdaki `if/elif/else` dallarının son ifadesi dönüş değeridir.

### Operatörler ve değerler
`+ - * / // % ** == != < <= > >= and or not in`. `true`, `false`, `none`. Metin `"..."`, içinde `{x}` ya da `{x:.2f}` ile değer yerleştirme. Liste `[1, 2]`, sözlük `{"a": 1}`, indeksleme `xs[i]`, `xs[-1]`, dilim `xs[a:b]` (liste ve metin). Liste üreteci `[E for x in xs if P]` de geçerlidir.

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
fail(msg: str)                          # sadece T! dönen fonksiyonda
```
Diğerleri (hepsi saf):
```
sayı:   abs round(x, n) min max sqrt floor ceil log exp int(x) float(x) str(x)
liste:  len sum avg unique flatten reverse sort first last take(xs, n) skip(xs, n)
        range(n) range(a, b) range(a, b, step) enumerate(xs) zip(a, b) any(xs) all(xs)
        find(xs, x) count(xs, x)            # find: yoksa -1
        append(xs, x) pop(xs)               # yerinde değiştirir, xs bir var olmalı
sözlük: keys values items get(d, k) get(d, k, default) dict(pairs)
metin:  split(s) split(s, sep) join(xs, sep) strip lstrip rstrip upper lower
        replace(s, old, new) starts_with ends_with chars is_digit is_alpha is_space
        ord chr find(s, sub) count(s, sub)
```
`first`, `last`, `get(d, k)` → `T?`. `int(s)`, `float(s)` geçersiz metinde hata verir (`?? 0` ile yakalanır).

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
