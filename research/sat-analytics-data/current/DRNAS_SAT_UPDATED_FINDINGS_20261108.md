# DRNAS SAT — kumulativni istraživački nalaz, 8. studenoga 2026.

**Stanje evidencije:** završni GitHub Actions auditi do 2026-11-08 19:20 UTC. 
**Baza:** `research/sat-analytics-data/current/sat_analytics.sqlite` (povijesna V15.3.1, sačuvana) + dodatne tablice `mre_audit_runs`, `mre_audit_attempts`, `mre_audit_scores` u verzioniranom SQLite artefaktu.
**Provjerena nova evidencija:** 8 auditiranih pokretanja, 1.892 stvarna SAT/UNSAT pokušaja i 52 odvojena moda/rezultata. Ne zbrajati međusobno različite PAR2 skupove i ne brojiti ponovljene originalne formule kao nove originalne formule.
**Dodatni strojno čitljivi zapisi:** `mre_audited_run_registry_20261108.json` i `mre_audited_modes_20261108.csv`, s izvornim run/job ID-ovima i oznakama podrijetla.

## A. Osnovni zaključak

DRNAS ima stvarne, reproducibilne, dokazivo sigurne strukturne redukcije u nekim formulama, ali **još nema potvrđenu statistički robusnu, opću nadmoć nad vodećim referentnim solverima na neviđenim originalnim formulama**. Najbolji razvojni primjer C++ Joint (MRE10) daje 1,257× i 1,209× na identičnom, ranije korištenom skupu, ali na novom referentno odabranom MRE10b skupu regresira na 0,882× i gubi dva riješena pokušaja.

Temeljna hipoteza koja ostaje živa: **selektivno, certificirano čišćenje i zamjena ekvivalentnih varijabli** mogu pomoći kada povoljno mijenjaju propagaciju/CDCL, ali samo smanjenje dimenzije formule ne predviđa pouzdano brzinu.

## B. Ponovljivi parovi i PAR2 (sekunde, manje je bolje)

Svaka brojka u nastavku dolazi iz uspješnog završnog SAT/UNSAT audita. Ubrzanje je omjer **PAR2 reference / PAR2 metode**, a ne razlika postotaka riješenih formula.

| Protokol / skup | Reference: riješeno i PAR2 | DRNAS varijanta: riješeno i PAR2 | Ubrzanje × | Napomena |
|---|---|---|---:|---|
| MRE10 prvi, 16 ranije korištenih originala, 4 seeda, 8 s | CMS N_ext 56/64; 211,756782 s | C++ Joint 58/64; 168,473602 s | **1,256914×** | Razvojni skup; 640/640 pokušaja |
| MRE10 ponovljeni, istih 16 SHA, seedovi, kod i 8 s | CMS N_ext 57/64; 196,430859 s | C++ Joint 58/64; 162,528832 s | **1,208591×** | Reproducibilnost na istom skupu; 640/640 |
| MRE10b novi, 12 originala SAT2023–25, 3 seeda, 15 s | CMS N_ext 26/36; 415,178377 s | C++ Joint 24/36; 470,811893 s | **0,881835×** | 2 dodatne regresije solved→timeout; 144/144 |
| MRE10b, isti novi skup | CMS N_ext 26/36; 415,178377 s | C++ Clean 26/36; 426,287736 s | **0,973939×** | Jedan dodatno riješen i jedan izgubljen pokušaj |
| MRE11b, 8 izvora SAT2021–23 odabranih bez DRNAS runtimea, 35 s | C++ Native 13/16; 319,895889 s | C++ Joint 14/16; 226,620410 s | **1,411593×** | Pozitivan prijenos na jedan novi uzorak; 128/128 |
| MRE11b, isti skup i limit, različiti solveri | C++ Native 13/16; 319,895889 s | CaDiCaL 16/16; 90,752491 s | **3,524927×** | CaDiCaL najbolji; Kissat 14/16, 207,035953 s |
| MRE11, 7 službenih SAT2026 originala, 4 seeda, 8 s | C++ Native 0/28; 448,000000 s | C++ Joint i C++ Selector 0/28; 448,000000 s | 1,000000× (cenzurirano) | NULA riješenih, nije dokaz jednake brzine; 140/140 |
| MRE6g, 6 SAT2026 (2 poznata, 4 referentna), 35 s | CMS+XOR 10/12; 243,410476 s | SCC+GF(2) 10/12; 245,178852 s | **0,992787×** | Matematika radi, ali ukupno sporije |
| MRE6h, isti miješani razvojni kohort, 35 s | CMS+XOR 9/12; 287,428032 s | Fast GF(2) bez importa 9/12; 287,492381 s | **0,999776×** | Brža priprema, PAR2 praktički jednako |
| MRE6i, 2 poznata + 4 nova službena + 2 sintetska, 35 s | CMS+XOR 12/16; 332,860886 s | Gate bez XOR importa 12/16; 333,328952 s | **0,998596×** | Nema sigurnog dobitka na četiri nova službena originala |

**Upozorenje:** MRE6g i MRE6h različito vremenski izvršeni razvojni eksperimenti istog tipa kohorta ne smiju se spojiti u jedan parni rezultat. Sintetske formule u MRE6i i korišteni razvojni izvori ne predstavljaju slijepi službeni benchmark. Referentni algoritam i limit mijenjaju se od protokola do protokola.

## C. Analiza uzroka, a ne samo zbirne brojke

1. **Formula SAT2025 `695d8f6a…` (poznati razvojni izvor):** C++ Joint uklanja **560 suvišnih klauzula (~17,8%)**, bez eliminacije varijabli. Prvi benchmark 46,505 s CMS prema 7,820 s Joint (5,95×); ponavljanje 35,641 s prema 6,508 s (5,48×). U ponavljanju ta jedna formula daje ~29,13 od ~33,90 s ukupne PAR2 uštede (**~86%**). Time potvrđujemo stvaran strukturni mehanizam, ali i snažnu koncentraciju prednosti na jedan izvor.
2. **Formula SAT2023 `fdfcd52a…`:** potvrđeno 1.318 certificirano eliminiranih ekvivalentnih varijabli i 7.361 uklonjena klauzula. Ponavljanje 11,228 s CMS prema 7,115 s Joint (1,58×). Originalni SAT model provjeren je nakon rekonstrukcije.
3. **Formula SAT2023 `037d21e0…`:** šest eliminiranih varijabli i 191 uklonjena klauzula, ubrzanje u ponavljanju 2,780/1,694 ≈1,64×.
4. **Formula SAT2024 `be6411f4…` (MRE10b, novi skup):** C++ Clean 3/3, 21,932 s; CMS 2/3, 40,806 s; Joint 1/3, 67,059 s. Na dovršenom Joint pokušaju uklonjeno 229 varijabli i 731 klauzula, a na timeoutima podaci o aktivaciji nisu završno ispisani. Zato se oba timeouta NE SMIJU automatski pripisati samom dokazivanju ekvivalencije.
5. **Formula SAT2023 `909f704d…` (MRE10b):** CMS riješi 1/3, Joint i Clean 0/3, bez potvrđene aktivne redukcije na tom izvoru. To je regresija ishoda, ali nije utvrđena matematička uzročnost (seed/runner i promijenjena obrada ulaza mogu biti dio uzroka).
6. **Formula SAT2025 `0e1d5620…` (MRE10b):** Clean uklanja 4.356 suvišnih klauzula po seedu, ali usporava PAR2 s 14,992 s na 22,710 s (sva tri pokušaja riješena). Broj uklonjenih klauzula NE MOŽE se izravno koristiti kao prediktor brzine CDCL.
7. **MRE6g/h/i GF(2) pravac:** dokazani, ponovno verificirani XOR→CNF zaključci, potpisane SCC ekvivalencije i ispravno rekonstruirani SAT modeli. Jedan poznati SAT2026 izvor ima četiri korisna spajanja; dva nova sintetska XOR/CNF izvora po pet. **Na četiri nova službena MRE6i izvora nije bilo certificiranih eliminacija**, a na sintetskim vrlo lakim formulama cijena dokaza nadmašuje rješavanje.
8. **MRE11 SAT2026:** svih 28 pokušaja po metodi doseglo je osam sekundi. Ovo je problem **cenzuriranja**; povećati limit ili izabrati srednje teške originalne formule, umjesto izvlačenja zaključka o jednakoj brzini.

## D. Stariji istraživački smjerovi — zasebno, bez nove reaudicije

- **R28** ostaje netaknuta sigurnosna referenca; ne spajati eksperimentalne, selektorske i dokazne promjene u stabilnu verziju bez zasebnog audita.
- **R63 XOR test na stvarnim originalima:** ranije prijavljeno 18/64 riješenih naspram 16/64 Kissat, PAR2 3.894,96 vs 4.055,17 s, uz većinu koristi koncentriranu u jednom čistom XOR izvoru. To podupire specijalističku, ne opću metodu.
- **R135 400-formula benchmark:** ranije prijavljeno 376/800, PAR2 12.889,82 s naspram Kissat 13.198,93 s (364/800); CaDiCaL 12.870,51 s (376/800). Prednost prema Kissatu, ali ne prema CaDiCaL-u. Postojale su i velike lokalne regresije.
- **R166x / R165 exact XOR router:** snažna selektivna korist na čistom XOR podskupu; nije prenesena na miješani CNF/XOR skup u istoj mjeri.
- **MRE9 bounded-CDCL:** diagnostika konflikata, propagacija i CPU nije zamjena za kompletno SAT/UNSAT rješenje ili PAR2. Nije dokaz općeg ubrzanja.
- Povijesna V15.3.1 analitička baza ostaje neizmijenjena; ove starije brojke nisu ponovno izvršene u zadnjem ingestu i ne pripisuju se osam novih auditiranih runova.

## E. Dokazni standard i ograničenja

- Završeni SAT modeli u osam novih audita verificirani su na **originalnom SHA-pinned CNF-u**, ne samo na reduciranom ulazu.
- UNSAT je provjeravan preko službenog statusa ili neovisnog referentnog solvera prema pojedinom protokolu, ali **nema neovisnih LRAT/DRAT dokaza** za sve UNSAT rezultate; ne koristiti izraz „potpuno formalno certificiran UNSAT” bez tog dokaza.
- Nisu svi testovi globalno slijepi: neki su development, neki izvan praćenih ranijih kohorta, neki odabrani prema referentnoj težini, a pojedini su sintetski. Evidencija namjerno čuva tu podjelu.
- PAR2 = zbroj stvarnog end-to-end wall vremena uspješno riješenih pokušaja + 2× vremenskog limita po timeoutu; ne spajati PAR2 sekunde različitih limita i skupova.
- Broj riješenih pokušaja među ponavljanjima MRE10 mijenja se čak i uz iste seedove, što potvrđuje osjetljivost realnog wall-time limita na izvršavanje.

## F. Istraživačke odluke po prioritetu

1. **Najprije reprodukcija i atribucija regresija.** Na originalima `be6411f4…` i `909f704d…` usporediti CMS, clean, rename, joint s 5–10 zamrznutih seedova, duljim 30–60 s limitima, pošteno serijalnim CPU mjerenjem i brojačima odluka, konflikata, propagacija. Ne podešavati gate na tim izvorima pa onda iste zvati holdoutom.
2. **Uzročno odvajanje dva modula.** `Clean only`, `Certified equality only`, `Joint`, `Native` na istim izvornim SHA i procesorima; testirati koristi li smanjenje clause visits ili promjena heurstičke topologije, a ne samo postotak uklonjenih klauzula.
3. **Selektor s opreznim abstainom.** Testirati jeftine izvorno vidljive značajke: udio binarnih implikacija, provjereni broj ekvivalentnih varijabli, dup/taut udio, očekivani trošak transformacije, veličina formule, kratka neaktivna dijagnostika. Svaka odluka prije punog solvea, bez informacija iz pobjedničkog solvera. Zamrznuti na razvojnom skupu pa provjeriti na novom SHA-disjunktnom skupu.
4. **Novi stvarni srednje teški SAT2023–2026 holdout**, minimalno 20–30 originala, 4 uparena seeda, isti CMS/Kissat/CaDiCaL reference, 30–60 s puni limit, 1 jezgra / stabilan CPU, bez uklanjanja timeouta. Prijaviti regresije i koncentraciju doprinosa najveće formule.
5. **LRAT/DRAT dokazni sustav za UNSAT**, originalna SAT provjera i zadržavanje R28 frozen fallbacka. Bez audita ne promovirati metodu u produkciju.

**Konačna procjena:** napredak u kvaliteti algoritamske interpretacije i revizijskom standardu je značajan. Kandidat s najviše *provjerenog praktičnog potencijala* trenutačno je originalno-CNF certificirana C++ redukcija (clean + equality), ali bez pouzdanog gatea uzrokuje regresije. Najbrži put do vjerodostojnog napretka nije daljnje povećavanje broja eliminiranih varijabli, nego razumjeti **kada i zašto redukcija mijenja CDCL trajektoriju** te dokazati to u novom službenom benchmarku.


## G. Naknadno pokrenuto, još NE upisano u potvrđenu bazu

**MRE11-L35:** GitHub run [42514613031](https://github.com/Frane12/AndroidGameTest/actions/runs/42514613031) je pri posljednjoj provjeri 2026-11-08 19:35 UTC **još u tijeku**. Dulji limit 35 s na istih sedam službenih SAT2026 originala, pet metoda i četiri seeda. Priprema i shard 3 bili su zeleni; shardovi 0, 1 i 2 još su se izvršavali. Nijedan rezultat iz tog nepotpunog runa nije dodan u 1.892 auditirane pokušaje niti mu je pripisan konačan PAR2. U novom ingestu ga dodati tek nakon završnog original-SHA SAT/UNSAT audita, ne kao predviđanje.
