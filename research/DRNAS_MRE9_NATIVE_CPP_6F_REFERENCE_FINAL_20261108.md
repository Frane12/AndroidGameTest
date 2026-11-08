# DRNAS MRE9 — Native C++ MRE6f reference, završni audit (8. 11. 2026.)

**Status:** eksperimentalni prototip; 270/270 source-paired pokušaja završilo je i prošao je završni audit. Dodatni native SAT/UNSAT smoke prošao je. **Bez produkcijske promocije.**

## Nepromjenjiva referenca
MRE6f: [run 42499854392](https://github.com/Frane12/AndroidGameTest/actions/runs/42499854392). MRE6e: [pinned shared CMS/source run 42499473274](https://github.com/Frane12/AndroidGameTest/actions/runs/42499473274), CMS source commit \`3b709118fd08eb1d15f25e0e239dbc596f967b60\`.

- Originalne dvije CNF binarne klauzule \`(-a OR b)\` i \`(a OR -b)\` čine dokazivo \`a ↔ b\`. Koristi se tranzitivna klasa i izvorno dokazna ekvivalencija. Nema nagađanih XOR zaključaka.
- Novi \`research/mre9_native_cms_gate.cpp\` **u istom C++ procesu** učitava originalni DIMACS, prepoznaje certifikate, opcionalno reducira CNF i predaje ga identičnoj SHA-pinned CryptoMiniSat 5.11.15 knjižnici, bez dodatnog Python reducera.
- Prije rezultata zamrznut gate: ≥128 eliminiranih varijabli, ≥256 uklonjenih klauzula, ≥8% uklonjenih klauzula; inače koristi izvornu formulu bez transformacije.
- Posebna standalone kompilacija iscrpno je testirala 48 malih formula × 64 dodjele; sam C++ zapis reduciranih klauzula poklapa se s MRE6f Python matematičkom referencom.
- Stvarni original SAT2026 pozitivan razvojni primjer \`2fcd8533...\`: 672 eliminirane varijable, 1.344 uklonjene klauzule (12,1387 %); native parse ~4,60 ms i C++ gate ~2,85 ms na smoke primjeru.

## 210 pokusa do ograničenog CDCL budžeta — 7 već testiranih originalnih SAT2026
7 originalnih SHA × 3 ponavljanja × 2 granice konflikata (1.000 i 5.000) × 5 armova = 210.
**Svaki arm ima 42 bounded UNKNOWN i 0 SAT/UNSAT rješenja. PAR2 = 504 s za svaki arm i NE smije služiti za rangiranje ubrzanja rješavanja.** Sljedeće su ukupna wall vremena do fiksnog broja konflikata, uključujući pripremu.

| Arm | Ukupno vrijeme (s) | Aktivacija | Propagacije (zbroj) |
|---|---:|---:|---:|
| CMS native, stara Python priprema | 7,472259 | 0/42 | 35.048.214 |
| MRE6f all, referenca | 7,868492 | 12/42 | 27.271.959 |
| MRE8f Python gate | 7,568426 | 6/42 | 27.271.965 |
| MRE9 C++ native bez redukcije | 5,863906 | 0/42 | 35.048.214 |
| **MRE9 C++ gate** | **5,423202** | **6/42** | **27.271.965** |

- \`CMS_native / cpp_gate = 1,378×\` — bounded-total-wall, **nije SAT-verdict brzina**.
- \`MRE8f_python_gate / cpp_gate = 1,396×\` — smanjenje režije u usporedbi sa starim gateom.
- \`cpp_native / cpp_gate = 1,081×\` — dobit od selektivne redukcije pored nativnog izvršavanja.
- C++ gate zbrojeno: 0,642845 s za native parse, 0,019255 s za gate. Ti su troškovi uključeni u ukupni wall, a ne zanemareni.
- \`2fcd8533...\` na 5.000 konflikata: CMS 6.147.559 propagacija, reducirani 3.990.542 (−35,087%). To reproducira MRE6f dijagnostički mehanizam.
- Slaba jednakost \`a45aefde...\`: C++ gate odbija redukciju; izbjegnuta MRE6f regresija s mnogo vremena u Python transformaciji.
- Audit je potvrdio da je **C++ odluka o gateu jednaka Python referenci na svakom uparenom ulazu**.

## 60 stvarnih pokušaja do SAT/UNSAT ishoda — MRE7 šest već korištenih lakih originala
6 originalnih SAT2024/25 SHA × 2 ponavljanja × 5 armova; limit 8 s, timeout PAR2=16 s. Svi solveri riješili su **6/12 SAT**, s **6/12 timeout**, te 0 aktivacija gatea. Originalni SAT modeli provjereni su protiv potpunog izvornog CNF-a.

| Arm | PAR2 (s) | Riješeno/12 | Gate |
|---|---:|---:|---:|
| CMS native | **113,244435** | 6 | 0 |
| MRE6f all | 113,333067 | 6 | 0 |
| MRE8f Python gate | 113,310664 | 6 | 0 |
| C++ native | 113,247300 | 6 | 0 |
| C++ gate | 113,297302 | 6 | 0 |

**Nema potvrđenog end-to-end ubrzanja:** C++ gate je oko 0,047% sporiji od starog CMS u ovom uzorku (vjerojatno vremenska varijacija/režija), a razlika je zanemariva. Na ovih šest formula nema strukturne aktivacije gatea, pa se ne može potvrditi njegova prednost u stvarnom rješavanju. Uzorak nije novi blind holdout i nema neovisno dokazanog UNSAT LRAT rezultata.

## Dodatni C++ model-lifting smoke
[Run 42506875238](https://github.com/Frane12/AndroidGameTest/actions/runs/42506875238) na **točno istom** već auditiranom MRE9/CMS binarnom artefaktu:
- **SAT_ACTIVE:** 259 eliminiranih varijabli; 818 uklonjenih klauzula; C++ gate **APPLY** i izvorni SAT model **neovisno verificiran** izvan C++ programa.
- **UNSAT_TRIVIAL_ROOT_ACTIVE:** C++ gate **APPLY**; namjerno kontradiktorne izvorne jedinice \`1\` i \`-1\` daju UNSAT. Ovo nije LRAT dokaz.
- **SAT_ABSTAIN_NO_EQ:** C++ gate **ABSTAIN**, izvornu formulu rješava i provjerava SAT witness.

## Protokol, rizici i sljedeći prioritet
1. Potvrđeno: nativni C++ drastično smanjuje trošak front-enda i čuva MRE6f matematički učinak na originalnom pozitivnom razvojnom slučaju.
2. Nije potvrđeno: ponovljivo ubrzanje realnog SAT/UNSAT PAR2 na reprezentativnom source-disjoint holdoutu.
3. Identična mat. redukcija, SHA, seed, backend library; izbjegava se naknadno izbacivanje loših formula i zamjena referentnog MRE6f protokola.
4. Sljedeći korak: prospektivno odabrati originalne neviđene SAT/UNSAT formule na kojima unaprijed definiran strukturni gate ima potencijal, uz **odvojenu nefiltriranu kohortu** za stvarnu generalizaciju; 30–90 s end-to-end PAR2, verificirani originalni SAT modeli, nezavisni UNSAT dokaz gdje postoji, i analizu regresija.
5. Ostaviti metodu samo u eksperimentalnoj grani dok ne pobijedi baseline na zaključanoj neviđenoj testnoj kohorti.

**Glavni audit:** https://github.com/Frane12/AndroidGameTest/actions/runs/42506543129

**Eksperimentalna grana:** \`experiment/drnas-mre9-native-cpp-6f-ref-20261108\`
