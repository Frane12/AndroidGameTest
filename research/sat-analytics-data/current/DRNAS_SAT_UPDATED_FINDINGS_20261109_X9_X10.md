# DRNAS SAT — X6–X10, ažurirani nalaz 9. studenoga 2026.

**Reproducibilnost:** stvarni GitHub Actions završni audit, isti izvorni SHA unutar protokola, E2E wall + CNF preprocessing, PAR2 timeout = 2 × 15 s. Potpuna povijesna evidencija je u postojećoj analitičkoj bazi; novi X9/X10 redci dodaju se u odvojene tablice bez prepisivanja V15.3.1.

## I. Odgovor: koliko smo bolji na X10?

- **X10** uspješan run [42561615100](https://github.com/Frane12/AndroidGameTest/actions/runs/42561615100), završni audit job **128981538691**, 32 originalna CNF SHA, 2 ponavljanja, 6 arms × 64 = **384** stvarna E2E mjerenja.
- Original CMS: **40/64**, PAR2 **827,193812 s**.
- **front100:** **41/64**, PAR2 **780,934128 s**. **1,059236×** u odnosu na original, **5,592 % manje PAR2**; **1,131626×**, **11,632 % manje PAR2** od Kissata; **1,161877×**, **13,932 % manje PAR2** od CaDiCaL-a. Samo ovaj specifični razvojni skup, ne opći benchmark.
- **spread_shifted:** **41/64**, PAR2 **784,057914 s**. **1,055016×**, **5,215 % manje PAR2** od originala; **1,127117×** i **11,278 % manje PAR2** od Kissata; **1,157248×** i **13,588 % manje PAR2** od CaDiCaL-a.
- **adaptive X10:** **40/64**, PAR2 **826,937157 s**, **1,000310×**, **0,031 % manje PAR2** od originala; **1,068673×**, **6,426 % manje PAR2** od Kissata; **1,097241×**, **8,862 % manje PAR2** od CaDiCaL-a.
- Kissat: **37/64**, PAR2 **883,725317 s**. CaDiCaL: **36/64**, PAR2 **907,349232 s**.
- Prividna prednost front100 nad druga dva referentna solvera djelomično je posljedica timeouta i njihovog 2× timeout bodovanja; nije dokaz univerzalne nadmoći.

## II. X10 adaptacija nije proradila

- Adaptivni gate je odabrao **original u svih 64/64 mjerenja**. KNN-5 na 48 KiB početka CNF-a i pozitivni pragovi bili su previše konzervativni.
- **front100 vs original:** 6 pobjeda, 15 poraza, 11 izjednačenja po izvorima (30 razvojnih plus 2 rezervirana).
- **spread_shifted vs original:** 5 pobjeda, 16 poraza, 11 izjednačenja.
- **adaptive vs original:** 12 pobjeda, 8 poraza, 12 izjednačenja; male razlike izmjerene su čak kad odabere isti backend i izvorni CNF (šum mjerenja), ne stvarni dokazi ubrzanja gatea.
- **32 izvora nisu slijepi:** 30 je već korišteno u X9, 2 rezervirana X6 Fresh. Obje rezervirane su **0/4** za sve solver konfiguracije i time ne pružaju validaciju na riješenim neviđenim problemima. Odvojena skupina X9 replay ima 30 SHA, 60 repova po modu, *front100* **41/60, 660,934128 s** vs CMS **40/60, 707,193812 s** (**1,069991×**). Različiti kapovi/protokoli se ne smiju spajati.

## III. X9 zamrznuti prethodni benchmark

- Uspješan run [42559879920](https://github.com/Frane12/AndroidGameTest/actions/runs/42559879920); final audit job **128976119563**; 30 pripremljenih originala × 2 × 5 = **300** E2E mjerenja; vremenski limit 15 s.
- CMS: **41/60**, PAR2 **697,469738 s**.
- **front100:** **41/60**, PAR2 **669,999126 s**, **1,041001×**, **4,10 % manje PAR2** od CMS-a; **1,160038×** Kissat; **1,223501×** CaDiCaL.
- **spread_shifted:** **41/60**, PAR2 **671,962846 s**, **1,037959×**, **3,66 % manje PAR2** od CMS-a.
- Kissat: **36/60**, PAR2 **777,224721 s**. CaDiCaL: **34/60**, auditarni PAR2 **819,744277 s** (sudjelovanje UNSAT bez dovoljne međusolverske potvrde penalizirano, pa se može razlikovati od sirovog iznosa prijavljenih vremenskih mjerenja).
- front100 pobjede/porazi/izjednačenja po formuli: **8/13/9**.

## IV. Najjače pojedinačne formule i njihova koncentracija

Iz X10 na dva mjerenja svake formule:

| GBD prefiks | CMS PAR2 | front100 PAR2 | Omjer CMS/front | Ušteda |
|---|---:|---:|---:|---:|
| `220bb8aa` | 33,765 s | 2,507 s | 13,47× | 31,26 s |
| `695d8f6a` | 9,230 s | 0,138 s | 66,88× | 9,09 s |
| `fdfcd52a` | 11,814 s | 5,059 s | 2,34× | 6,76 s |

Te tri formule zajedno čine približno **47,1 od 46,26 sekundi** neto X10 uštede naspram originala: ostale formule zajedno blago regresiraju. Najveći zadatak jest identificirati formulu prije rješavanja koja će imati korisnu watch/propagation promjenu.

## V. Dosadašnji razvojni slijed, bez miješanja skupova

- X6 Easy, run [42558073981](https://github.com/Frane12/AndroidGameTest/actions/runs/42558073981): na 9 poznatih lakših originala `front100` **12,375996 s** vs CMS **13,238380 s**, **1,069682×**; Kissat **20,282283 s**. Režija preraspodjele je značajna na jednostavnim zadacima.
- X7, run [42556906957](https://github.com/Frane12/AndroidGameTest/actions/runs/42556906957): razvojni skup 4 formula × 4 seeda × 6 arms, `spread_shifted` **16,580094 s** vs CMS **129,064165 s**, **7,784284×**, uz timeoute CMS-a; nije blind.
- X8, run [42558264803](https://github.com/Frane12/AndroidGameTest/actions/runs/42558264803): 4 ranije poznate formule, 2 seeda, `spread_shifted` **4,515562 s** vs CMS **56,124463 s**, **12,42912×**, 8/8 naspram 6/8; instrumentirani CMS binarni digest različit od X7 pa omjeri nisu usporedivi bez kontrole.
- X9: širi replay 30 formula — prednost `front100` se smanjuje na 1,041×.
- X10: replay+2 rezervirane formule — `front100` 1,059×, ali kNN adaptivni model 1,00031×.
- Stariji MRE10 C++ Joint na istom razvojnom skupu 1,257× odnosno 1,209× na ponavljanju, dok je u novom MRE10b skupu **0,882×** uz gubitak 2 riješene instance. Izričit podsjetnik da replay prednost može nestati na novim formulama.

## VI. Mehanizam, interpretacija i ograničenja

- Transformacija je **permutacija multiskupa izvornih CNF klauzula**, bez promjene logike. X7/X8 native trace pokazuje da watch-list reda i rani razlozi implikacija mogu promijeniti naučene klauzule, odluke i vrijeme. Nisu sve formule takve: na mnogima je put identičan, a jedina promjena je dodatna priprema.
- To nije CRR/XOR matematička redukcija ni novi solver koji dominira svijetom. Trenutačno je **instance-specifična mikroarhitektura CDCL ulaza**.
- SAT modeli provjereni na originalnom CNF-u. UNSAT nema nezavisnog LRAT dokaza; bodovanje za nepotvrđeni UNSAT koristi 2× timeout. Nema automatskog promoviranja.
- Razlika postotaka PAR2 može biti nestabilna s malim uzorkom, velikim timeout penalizacijama, različitim runner resursima i ponovno korištenim izvorima.

## VII. Idući prioritet: X11 Causal Duplicate-Position Ablation

Ne širiti model koji nikad ne aktivira. Prvo napraviti dokaziv, *jeftin* strukturni gate na stvarnom položaju i broju jednakih klauzula, a zatim testirati dozu i redoslijed (front25/front50/front100, eventualno samo binarne duplikate) protiv izvornog CMS-a i referenci, uz strogu istu multiset potvrdu. Za učenje koristiti leave-one-source-out/nested postupak bez uključivanja rezultata ispitivane formule. Svaki izvor iz X9 je poznati razvojni uzorak; sljedeći vjerodostojan korak nakon mehanizma su novi, slijepo zamrznuti i dokazivo rješivi originali u više kategorija.

## VIII. Baza i načelo evidencije

Ažuriranje u odvojenu granu `experiment/drnas-analytics-x9x10-20261109`; dodatne tablice `mre_x9x10_runs`, `mre_x9x10_attempts`, `mre_x9x10_scores` čuvaju **684 E2E pokušaja** i **11 auditiranih arm scoreova**, uz run ID, SHA-256 manifesta i izvješća, SHA formule, seed, odabrani backend, mode, preliminarni i auditarni PAR2 i dokazne zastavice. Baza V15.3.1 i prethodni MRE namespace ostaju nepromijenjeni. Spajanje PAR2 vrijednosti iz različitih protokola nije dopušteno.
