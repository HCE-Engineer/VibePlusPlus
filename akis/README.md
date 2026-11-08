# Akış v0.1 transpiler

Akış (`.aks`) → Python 3.11. Şartname: `spec/AKIS_SPEC.md`, değişiklikler: `spec/CHANGELOG.md`. Parser: Lark (LALR + girinti post-lexer). Tip ve efekt denetimi statik;
denetimden geçmeyen kod Python'a çevrilmez.

```bash
python3.11 -m venv .venv-akis && .venv-akis/bin/pip install -r requirements-akis.txt
bin/akis check sol.aks            # her hata tek satır JSON, çıkış kodu 1
bin/akis build sol.aks -o sol.py  # üretilen kod `import akis_rt` yapar: PYTHONPATH'e runtime/ ekleyin
.venv-akis/bin/python -m pytest -q akis/tests
```

| Dosya | İçerik |
|---|---|
| `grammar.lark` | Dilbilgisi |
| `parser.py` | Kaynak → AST, sözdizimi hataları ve düzeltme ipuçları |
| `types.py` | Tipler (kademeli: `unknown` her şeyle uyumlu) |
| `checker.py` | Tip/efekt denetimi, E1/E2/N1/N2 kuralları |
| `codegen.py` | AST → Python |
| `../runtime/akis_rt.py` | Yerleşikler ve akış aşamaları |

## Hata kodları

| Kod | Anlamı |
|---|---|
| `E-SYNTAX-01` | Ayrıştırma hatası |
| `E-SYNTAX-02` | Tab karakteri |
| `E-SYNTAX-03` | Tutarsız girinti (hiçbir üst bloğa dönmeyen dedent) |
| `E-SYNTAX-04` | Geçersiz yapı: döngü dışında `break`/`continue`, `sort`/`sort_by` dışında `desc`, geçersiz atama hedefi |
| `E-TYPE-01` | Tip uyuşmazlığı |
| `E-TYPE-02` | Bilinmeyen isim/fonksiyon, `it` aşama dışında |
| `E-TYPE-03` | Bilinmeyen alan, `.0` hatalı kullanımı |
| `E-TYPE-04` | Argüman sayısı/isim hatası |
| `E-TYPE-05` | `T!` değeri `?` veya `??` olmadan kullanıldı ya da atıldı |
| `E-TYPE-06` | Fonksiyon dönüş değeri üretmeden bitebilir |
| `E-TYPE-07` | `let` bağlamaya veya parametreye atama |
| `E-TYPE-08` | Bilinmeyen tip adı |
| `E-TYPE-09` | `any`, `use py` dışında kullanıldı |
| `E-TYPE-10` | Çift tanım |
| `E-TYPE-11` | `fail()` dönüş tipi `T!` olmayan fonksiyonda |
| `E-TYPE-12` | Hesaplanan değer kullanılmıyor (`sort(xs)` tek başına, `x == 1` yerine `x = 1`) |
| `E-EFFECT-01` | Kural E1 ihlali |
| `E-EFFECT-02` | Bilinmeyen efekt adı |
| `E-NEST-01` | Kural N1 ihlali (3 seviyeden fazla) |
| `E-NAMEDARG-01` | Kural N2 ihlali; kayıt oluştururken isimsiz alan |
| `E-QMARK-01` | Kural E2 ihlali |

## Şartnamenin açık bıraktığı yerlerde verilen kararlar

Şartnamenin söylemediği noktalarda uygulamanın yaptığı seçimler (modele verilen metinde yer almazlar):

1. **Kayıtlar çalışma zamanında `dict`**: `Part(name: "a", weight: 1.0)` → `{"name": "a", "weight": 1.0}`,
   `p.name` → `p["name"]`. Böylece aynı `test_hidden.py` iki kolu da test eder (Python imzasında `TypedDict`).
2. **Boşluk miktarı zorlanmaz**: tutarlı her girinti kabul edilir; `|` ile başlayan satır önceki akışın devamıdır.
   Tab yasak.
3. **`T!` katı, `T?` gevşek**: `T!` değeri `?`/`??` olmadan kullanılamaz (`E-TYPE-05`). `T?` değeri `T` yerine
   kullanılabilir (akış daraltması yok).
4. **Blok kapsamı**: `let`/`var` tanımlandığı blokta görünür; iç bloktaki aynı isim dıştakini gölgeler.
5. **Koşullar** her tipte olabilir (Python doğruluk değeri).
6. **`for k in d`** anahtarları gezer (Python gibi); akış ise `(anahtar, değer)` verir (şartnamede yazılı).
7. **`min`/`max`/`avg`/`max_by`/`pop`, olmayan indeks/anahtar** `AksError` fırlatır; tipleri `T!` değil `T`
   sayılır. Böylece `?? varsayılan` çalışır, ama `?` zorunlu olmaz.
8. **`append`/`pop`/eleman ataması** kök değişkenin `var` olmasını ister (`E-TYPE-07`). Parametre listesi önce
   kopyalanmalı: `var ys = xs[:]`.
9. **`+=`** üretilen Python'da `x = x + v` olur (liste takma adı yerinde değişmesin diye).
10. **`use py ... -> T!`** ile alınan fonksiyonun her Python istisnası `AksError`'a çevrilir. `use py` fonksiyonları
    N2'den muaftır (parametre adları bilinmiyor).
11. **Şartnamede yazmadan kabul edilenler**: `True/False/None`, tek tırnaklı metin, fn başlığı sonunda `:`,
    `startswith/endswith/isdigit/isalpha/isspace/sorted/reversed/mean/to_dict` yazımları, `join` argümanlarının
    iki sırası (`join(xs, sep)` ve `", ".join(xs)`).
12. **`-> R` yazılmazsa** dönüş tipi `none`.
