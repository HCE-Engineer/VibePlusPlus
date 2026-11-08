# Akış v0 dil şartnamesi

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
