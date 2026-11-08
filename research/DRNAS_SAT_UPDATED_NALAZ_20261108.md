# DRNAS SAT — UPDATED NALAZ (PAR2, signali, anomalije)

**Vrijeme presjeka:** 2026-11-08 oko 18:01 CET.  
**Status:** razvojni istraživački nalaz, bez automatske promocije u produkciju.  
**Načelo:** razlikovati solver-verdict PAR2 od bounded-CDCL dijagnostike, stvarni DRNAS učinak od pobjede već postojećeg backenda, te dokaz matematičke ispravnosti od dokaza ubrzanja.

## 1. MRE7 Pilot6 — 6 originalnih SAT2024/2025 formula

[Run 42502481195](https://github.com/Frane12/AndroidGameTest/actions/runs/42502481195): 6 izvora, 2 ponavljanja, 4 varijante, ukupno 48 pokušaja; limit 8 s, PAR2 timeout 16 s. Originalni SAT modeli su verificirani; nisu dostupni neovisni UNSAT LRAT dokazi.

| Arm | Ukupni PAR2 (s) | Riješeno/12 | Timeout/12 |
|---|---:|---:|---:|
| cms_native | **82.745135** | 9 | 3 |
| all_equalities | 83.073539 | 9 | 3 |
| gate_auto | 83.090584 | 9 | 3 |
| kissat | 160.178077 | 2 | 10 |

Kissat/CMS_native = **1.936x**, Kissat/gate_auto = **1.928x** PAR2 omjer. **To NIJE dokaz 1.93x ubrzanja uzrokovanog DRNAS-om**, jer gate_auto odbija aktivaciju svih 12 puta, a all_equalities ne pronalazi transformacije na ovom pilotu. Gate/native PAR2 = 1.0042x sporije (~0.42%). Sam pilot nije prospektivni 20+ holdout, izvori su referentno predodabrani, a povijesni registar nije globalno potpun. Ne promovirati.

## 2. MRE7 Medium — 35 s stvarni SAT2026

[Run 42500214333](https://github.com/Frane12/AndroidGameTest/actions/runs/42500214333): 6 formula x 2 ponavljanja x 4 arma = 48 mjerenja, 2 poznate razvojne formule i 4 novije reference-medium formule.

**Samo 4 novije formule (8 pokusa po armu):**

| Arm | PAR2 (s) | Riješeno/8 |
|---|---:|---:|
| cms_native | 308.295923 | 4 |
| cms_source_xor | 272.424408 | 5 |
| mre6b_proof_quotient | 274.525456 | 5 |
| mre7_cpu_guard | **225.106641** | **6** |

Omjer native/guard PAR2 = **1.3696x**. Na formuli `09637d3b...` native 0/2 (PAR2 140 s), a guard 2/2 (PAR2 56.171895 s). VAŽNO: log pokazuje `fallback_CMS_XOR`, ne aktiviranu originalno certificiranu equality redukciju, pa ovaj rezultat nije dokaz matematičke prednosti MRE. Premalen skup i selekcija po referentnoj težini; potreban dodatni paired, identični seedovi i izolacija uzročnosti. Bez promocije.

Za svih 6 formula zajedno, PAR2 = cms_native 336.551950, cms_source_xor 296.728941, mre6b_proof_quotient 298.437219, mre7_cpu_guard 250.805117 s. Kohorte miješaju nove i stare, stoga prvenstveno prijaviti gornji noviji podskup.

## 3. MRE6d — nedokazan end-to-end učinak

[Run 42496742982](https://github.com/Frane12/AndroidGameTest/actions/runs/42496742982): 7 originalnih SAT2026 formula, 4 arma, 2 ponavljanja, limit 90 s: **0 riješenih / 14 po armu; PAR2 = 2520 s po armu**. Ovo ne rangira brzine solvera. Dokazane pozitivne jednakosti na 2/7 formula. Na `2fcd8533...`, 11072 -> 9728 klauzula (−12.14%), uklonjeno 672 varijable; drugi izvor `a45aefde...` ostvaruje samo 9 klauzula i 4 varijable uštede.

## 4. MRE6e/f — najbolji dosadašnji uzročno zanimljiv DIJAGNOSTIČKI signal

[Run MRE6e](https://github.com/Frane12/AndroidGameTest/actions/runs/42499473274); [Run MRE6f](https://github.com/Frane12/AndroidGameTest/actions/runs/42499854392). MRE6f: 72 bounded-CDCL pokušaja, 3 izvora, 3 ponavljanja, limiti 1000/5000 konflikata. **Nijedan pokušaj nije riješio SAT/UNSAT**.

Na post-hoc pozitivnoj razvojnoj formuli `2fcd8533...` s 5000 konflikata: 6,147,559 -> 3,990,542 propagacije (−35.087%), ukupni geomean baseline/all 1.208918x. Vremena tri para (s): 0.433338/0.365060; 0.432385/0.349957; 0.440878/0.365971. Brojila su ista po seedovima; timing potvrđen, ne tri neovisne pretraživačke putanje.

Negativna kontrola `a45aefde...`: pri 5000 konflikata geomean baseline/all = 0.50071x (oko 2x sporije uz pripremu). Dakle signal je stvaran, ali gate mora preskočiti male redukcije i mora uračunati cijeli wall.

## 5. MRE4 P3 Q1 — razvojni signal za R28

[Run 42494099280](https://github.com/Frane12/AndroidGameTest/actions/runs/42494099280): 40 SHA, 6 varijanti, 2 ponavljanja = 480 mjerenja, razvojna/kombinirana kohorta, nije blind source holdout. Na svih 80 pokušaja po armu CMS native PAR2 = 782.178142 s, R28 safe = 761.014665 s (~1.0278x native/R28); riješenih 68/80 u obje varijante. Equality quotient = 782.968832 s, bez neto prednosti. R28 očuvan, ne tvrditi novi rekord.

## 6. CRR1-B8 — nema aktivnog učinka

[Run 42500265299](https://github.com/Frane12/AndroidGameTest/actions/runs/42500265299): od 24 originalna SAT2025 scout izvora niti jedan nije medium-eligible. Kontrola `2d0c041c-hgen` imala je 2 SAT ponavljanja po armu, 0 dodanih klauzula; PAR2 = Kissat 3.677523 s, B3 loose8 3.691680 s, B5 multi8 3.681638 s. U ovom eksperimentu nema dokaza ubrzanja ili nove CDCL propagacije.

## 7. Status većeg MRE7 testa na presjeku

[30-source source freeze](https://github.com/Frane12/AndroidGameTest/actions/runs/42502156252) i [30-source four-arm paired benchmark](https://github.com/Frane12/AndroidGameTest/actions/runs/42502215957) bili su `in_progress`. Nema poštenog ukupnog PAR2 ni zaključka. Raniji prospektivni run [42501527378](https://github.com/Frane12/AndroidGameTest/actions/runs/42501527378) pao je u freeze/pripremi, ne u validiranom solver benchmarku. Ponovljeni Pilot6 prošao je nakon ispravaka.

[Official 2021–2023 source scout](https://github.com/Frane12/AndroidGameTest/actions/runs/42502728698) je završio: po 400 pregledanih GBD ID-jeva godišnje, 1174 jedinstvena ID-a i 25 već viđenih u vidljivom registryju; Minisat1m oznaku imaju 15 (2021), 14 (2022), 49 (2023). To je samo potencijalni bazen za daljnje provjeravanje, ne nova zbirka potvrđenih neviđenih benchmarka.

## 8. Prioriteti i pravila promocije

1. **Razdvojiti uzroke:** dokazati je li MRE7 medium dobitak posljedica fallback_CMS_XOR, ulaznog redoslijeda, seeda ili varijacije izvođenja. Sve četiri varijante pokretati u istom izvornom kontekstu uz poseban R28 kontrolni arm.
2. **Gate minimalnog matematičkog dobitka:** i dalje fail-closed; promatrati ukidanje klauzula/varijabli i mjerenu cijenu prep. Gate iz MRE7 protokola zahtijeva >=64 ukinute klauzule, >=6% klauzula, >=32 eliminirane varijable, >=4% varijabli; taj prag je hipoteza, nije već potvrđen.
3. **Službeni prospektivni originali:** završen 20–30+ SHA-locked skup, bez post-hoc izbacivanja; prijaviti solved, original witness, UNSAT proof status, PAR2 i sve regressions.
4. **Cross-representation redukcija:** tražiti nove dokazivo prenosive GF(2), CNF i grafne strukture koje uistinu uklanjaju potrebu za pretraživanjem, ne samo pasivne redove/klauzule koje ništa ne propagiraju.
5. **Nema produkcijske promocije** dok novi tretman nema dokaziv, ponovljiv, pozitivan end-to-end PAR2 na source-disjoint testu i nikakve nezaključene ispravnosne probleme.

### Sažetak

- **Najveća potvrđena PAR2 razlika u aktualnom Pilot6:** CMS 82.75 s vs Kissat 160.18 s (~1.94x), ali *bez DRNAS aktivacije*.
- **Najzanimljiviji noviji PAR2 signal:** MRE7 CPU guard 225.11 s vs native 308.30 s (~1.37x) na 4 nove SAT2026 reference-medium formule; nije uzročno potvrđena matematička redukcija.
- **Najbolji matematički mehanistički signal:** MRE6f −35.09% propagacija, ~1.21x end-to-end **bounded segment**, ali bez solver verdicta.
- **Zaključak:** matematički smjer ima potencijal i dobio je konkretne dijagnostičke signale; još nema potvrđenog prospektivnog end-to-end DRNAS ubrzanja na reprezentativnom neviđenom skupu.
