# Provjera na lakšim i srednje teškim stvarnim SAT formulama

14. studenoga 2026. Lokalno mjerenje, jedan logički CPU, isti zamrznuti izvršni program kao u prethodnom Simon testu.

**Ubrzanje na srednje teškim formulama nije potvrđeno.** Brža priprema ostaje mjerljiva, ali ukupno vrijeme pretrage dominira. Sva tri intervala za ukupni dobitak obuhvaćaju nulu.

200/200 mjerenih pokušaja verificirano: 120 SAT modela i 80 UNSAT DRAT dokaza. Nema timeouta. Dodatnih 20/20 zagrijavanja također je verificirano.

## Uzorak i protokol

Odabrano je pet originalnih SAT Competition 2024 formula, prethodno dvaput verificirano riješenih izvornom DRNAS OFF ili X5_NO_MIN referencom. Tri formule povijesno su trajale 0.05–5 s; dvije vrlo brze su odvojene kontrole. Ovo je provjera prijenosa opće optimizacije pripreme izvan Simona. Uzorak nije filtriran po potpunim AND definicijama i nije dokaz o nelinearnoj metodi.

10 ponavljanja × 5 izvora × BASE/INPLACE/Kissat/CaDiCaL. Native BASE i INPLACE idu neposredno jedan za drugim uz izmjenu redoslijeda; sve je serijsko na jednom CPU-u. Nelinearni prioritet odluka i DELTA4X matematika su isključeni u oba native režima. Nema novih izmjena solvera.

Granica je 5 s za solver i odvojeno 25 s za neovisni provjerivač. Vrijeme u tablici uključuje pokretanje procesa, parsiranje, pretragu i ispis modela/dokaza. Trošak neovisne provjere zabilježen je posebno.

## Medijani vremena

| Formula | Razred | BASE | INPLACE | Promjena vremena | Kissat | CaDiCaL |
|---|---|---:|---:|---:|---:|---:|
| Break_unsat_04_03.xml | easy_control | 8.052 ms | 8.158 ms | +1.32% | 16.414 ms | 8.099 ms |
| worker_20_40_20_0.95 | easy_control | 8.987 ms | 8.668 ms | -3.56% | 37.840 ms | 78.035 ms |
| Break_unsat_06_07.xml | medium | 3695.858 ms | 3726.890 ms | +0.84% | 600.291 ms | 582.210 ms |
| ITC2021_Early_3.xml | medium | 224.103 ms | 218.618 ms | -2.45% | 225.039 ms | 158.836 ms |
| Break_08_24.xml | medium | 67.820 ms | 70.344 ms | +3.72% | 70.128 ms | 400.672 ms |

Negativna promjena vremena znači ubrzanje. Razredi su povijesne oznake za ovaj mali uzorak, ne opća klasifikacija težine.

Za tri dulje formule zbroj medijana raste za 0.70%, dok je razlika u zbroju svih PAR2 vremena samo 0.011% u korist INPLACE. Rezultat je praktički izjednačen, bez potvrđenog poboljšanja.

## Što se promijenilo

Na ITC2021_Early_3 medijan pripreme pada s 33.108 na 23.404 ms, ali ukupno vrijeme pada samo 2.45%, uz interval koji uključuje nulu. Na najduljem Break UNSAT-u priprema traje oko 1.5 ms prema približno 3.7 s pretrage; uklanjanje svih troškova pripreme ondje ne bi moglo donijeti značajan dobitak.

Na Break_08_24 novi medijan je 3.72% sporiji; i taj interval obuhvaća nulu. Nijedan slučaj nije uklonjen zbog nepovoljnog rezultata.

Svih 50 native parova ima iste odluke, konflikte, propagacije, naučene klauzule i restarte. Dodatno je svih 20 parova UNSAT dokaza identično po SHA-256, a svih 30 parova SAT izlaznih modela identično po bajtovima.

**Preporuka:** izmjenu pripreme zadržati kao eksperimentalnu optimizaciju za kratke slučajeve, ali ne proglašavati općim ubrzanjem. Za dulje slučajeve treba smanjiti trošak same CDCL pretrage. Ovim testom nije dodana nova heuristika.

## Trag i ponavljanje

`medium_cohort.json` sadrži izvorne SHA-256, ranija verificirana mjerenja i nazive formula. `medium_report.json` sadrži fazna vremena, medijane i opisne bootstrap intervale. `medium_trials.jsonl.gz` sadrži svih 200 pojedinačnih rezultata i hasheve provjerenih UNSAT dokaza.

Testirani binarni SHA-256: `7c11ef877f18fea0e6f84e2445aa1bb4cc295245dcabfd81477b7528fc3cd81a`. Generirani C++ SHA-256: `b1b6bc8ddd870f4d0c7dd78ffeec0009df4d3459596980d4e948424aa9a273cb`.

Ručni workflow: `.github/workflows/drnas-medium-solved.yml`. Pri ponovnoj kompilaciji dopušta se drugačiji hash izvršnog programa uz identičan provjeren generirani izvor; obje native konfiguracije i dalje koriste isti izvršni program. CI ponavljanje nije pokrenuto u ovom razgovoru.

Ovo je retrospektivan test pet formula iz scheduling zadataka; samo tri imaju dulje vrijeme. Ne podržava zaključak o svim SAT obiteljima ili slijepoj generalizaciji.
