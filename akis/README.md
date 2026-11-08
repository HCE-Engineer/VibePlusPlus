# Akış v0 transpiler

Akış (`.aks`) → Python 3.11. Parser: Lark (LALR + girinti post-lexer). Tip ve efekt denetimi statik;
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
| `E-SYNTAX-04` | Ayrıştırılan ama Akış v0'da olmayan yapı: `+=`, `break`/`continue`, `for a, b in`, dilimleme, liste üreteci, metot çağrısı |
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
| `E-EFFECT-01` | Kural E1 ihlali |
| `E-EFFECT-02` | Bilinmeyen efekt adı |
| `E-NEST-01` | Kural N1 ihlali |
| `E-NAMEDARG-01` | Kural N2 ihlali; kayıt oluştururken isimsiz alan |
| `E-QMARK-01` | Kural E2 ihlali |

## Şartnamenin açık bıraktığı yerlerde verilen kararlar

Şartname (`spec/AKIS_SPEC.md`) değiştirilmedi. Aşağıdakiler şartnamenin tanımlamadığı noktalarda
uygulamanın yaptığı seçimlerdir; modele verilen metinde yer almazlar.

1. **Bool sabitleri** şartnamede yok: `true`/`false` ve `True`/`False` ikisi de kabul edilir. `none`/`None` da.
2. **Kayıtlar çalışma zamanında `dict`**: `Part(name: "a", weight: 1.0)` → `{"name": "a", "weight": 1.0}`,
   `p.name` → `p["name"]`. Böylece aynı `test_hidden.py` iki kolu da sözlüklerle test eder
   (Python imzasında `TypedDict` kullanılacak).
3. **Boşluk miktarı zorlanmaz**: 2 boşluk girinti ve 4 boşluk devam satırı kuralları denetlenmez, tutarlı her girinti
   kabul edilir. `|` ile başlayan her satır önceki akışın devamıdır. Tab yasaktır (`E-SYNTAX-02`).
4. **`T!` katı, `T?` gevşek**: `T!` değeri `?`/`??` olmadan kullanılamaz (`E-TYPE-05`). `T?` değeri `T` yerine
   kullanılabilir (akış daraltması yok); `none` hatası çalışma zamanında test hatası olarak görünür.
5. **`fail()` sadece `T!` dönen fonksiyonda** (`E-TYPE-11`), "T! hata dönebilir" tanımından çıkarıldı.
6. **Blok kapsamı**: `let`/`var` tanımlandığı blokta görünür. İç blokta aynı isimle yeni `let` dıştakini gölgeler,
   üretilen Python'da ayrı isim alır.
7. **Koşullar** her tipte olabilir (Python doğruluk değeri).
8. **Sözlük üzerinde akış** `(anahtar, değer)` demetleri verir (`group_by ... | map (.0, .1 | len)`).
   `for k in d` ise anahtarları gezer (Python gibi).
9. **Son satır `if/elif/else` ise** her dalın son ifadesi dönüş değeridir.
10. **Aşama yerleşikleri fonksiyon olarak da çağrılabilir**: `len(xs)`, `sum(xs)`, `take(xs, 2)`. `min`/`max` ayrıca
    `max(a, b)` biçiminde çok argüman alır.
11. **`min`/`max` boş listede `AksError` fırlatır**, tipi `T!` değil `T` sayılır. `xs | max ?? 0` çalışır.
12. **`??` sadece `AksError` ve `None` yakalar**. Liste aralık dışı ve eksik sözlük anahtarı Python'un
    `IndexError`/`KeyError` hatasıdır ("çalışma zamanı hatası"), `??` bunları yakalamaz.
13. **`var` üzerinde eleman ataması** kabul edilir: `d[k] = v`, `xs[i] = v`, `p.alan = v` (kök değişken `var`
    olmalı). Şartname bunu açıkça tanımlamıyor; "var değiştirilebilir" ifadesi böyle yorumlandı.
14. **N2** akıştaki örtük ilk argümanı da sayar: `x | clamp(low: 0, high: 255)`. `use py` fonksiyonlarının parametre
    adı olmadığı için N2'den muaftır.
15. **`use py ... -> T!`** ile alınan fonksiyonun her Python istisnası `AksError`'a çevrilir.
16. **Metin**: kaçışlar `\n \t \" \\ \{`, `{{`/`}}` düz parantez. `{x}` Python `str(x)` ile yerleştirilir.
17. **`-> R` yazılmazsa** dönüş tipi `none`.
18. `?` her değere uygulanabilir (Python'da etkisizdir: hatalar istisna olarak zaten yukarı çıkar).
