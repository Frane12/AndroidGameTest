# R155 — Certified Mixed XOR → CNF Closure

**Datum:** 2026-11-05  
**Status:** samo eksperimentalna grana; nema promocije zamrznutih R153/R28 ili main.

## Zašto

R154 je na 25 SHA-odvojenih formula ostvario 26/50 riješenih s R153 naspram 14/50 s R28 i 0/50 s čistim Kissatom/CaDiCaL-om (15s cap). Ali sva četiri *mixed_residual* originalna CNF-a ostala su timeouti. R153 certificira potpune XOR blokove i izvorne unit klauzule te može dokazati kontradikciju ili potpuno pokriven SAT; kad je XOR sustav konzistentan i postoje obične klauzule, ostavlja korisnu GF(2) informaciju neiskorištenom i vraća se na čisti Kissat.

**Hipoteza R155:** kratki točni GF(2) zaključci (1–4 varijable), izvedeni Gauss–Jordan redukcijom odvojivih potvrđenih izvora, mogu pomoći standardnom CDCL-u na mješovitim originalnim formulama.

## Sigurna implementacija

- Polazište je *neizmijenjeni* izvorni `research/r153_exact_units_gf2.cpp`; R155 je nova kopija `research/r155_mixed_xor_closure.cpp`.
- Samo **potpuni** XOR sign-mask obrasci iz originalne CNF i **doslovne izvorne jedinične klauzule** su ravnopravne egzaktne GF(2) jednadžbe. Nikad se ne tvrdi da nepotpuni XOR obrazac predstavlja paritetnu jednadžbu.
- Postojeća R153 eliminacija zadržana: ako GF(2) podskup dokaže UNSAT, ostaje neovisan izvorni XOR certifikat; ako je cijeli CNF XOR-pokriven, daje model provjeren na izvornim klauzulama.
- **Novo samo za mješovite formule**: precizna Gauss–Jordan redukcija dokazanih paritetnih jednadžbi, iz svake kratke izvedene jednadžbe 1–4 varijable nastaju pripadne (2^(k−1)) CNF klauzule. Najviše 128 izvedenih jednadžbi/384 dodatnih klauzula; ograničenje native detekcije prije dodatnog procesiranja 200 ms i ≤2.000 početnih jednadžbi.
- Originalni CNF nije promijenjen. Privremeni prošireni DIMACS nastaje u **već unlinkanom** file descriptoru (`/proc/self/fd`); automatski se uklanja završetkom procesa. Nakon izgradnje, bez novih vlastitih SAT tvrdnji, pokreće se SHA-pinirani neizmijenjeni Kissat. Unsupported/over-budget mješovite formule idu na izvorni Kissat.
- Za svaki `c R155_DERIVED_EQ` **odvojeni Python verifier** ponovno prepoznaje egzaktne XOR obrasce iz originalnih klauzula, gradi vlastitu GF(2) bazu i provjerava pripadnost izvedene jednadžbe izvornom linearno generiranom prostoru. Ako bilo koja jednadžba nije logički implicirana, test odmah pada; nema pozitivnih izvješća.
- SAT model svakoga solvera provjeren je na svim originalnim klauzulama. Pure GF(2) UNSAT dokazi iz R153 mehanizma neovisno se rekonstruiraju. Ako prošireni CNF Kissat vrati UNSAT, taj rezultat **nema neovisni LRAT dokaz** — iako je dodana formula logički implicirana; taj dokazni status se mora jasno označiti.

## Prvi DEVELOPMENT benchmark

- Identitetski isti originalni SHA-verified izvori iz R154 `run 42107642696`; 25 originalnih formula, 7 potpuni XOR, 6 XOR+unit, 4 mixed residual, 8 bez XOR, **već javno analizirani**.
- Šest stvarno pokrenutih modova: R155, frozen R153, frozen R28, čisti Kissat 4.0.4, CaDiCaL 3.0.1, CryptoMiniSat Ubuntu 24.04.
- 2 ponavljanja/izvor, 15 s limit i timeout PAR-2=30 s, 8 shardova, max 4 u paraleli; **300 uparenih mjerenja**.
- Jednaki SHA-pinirani binarni buildovi (među shardovima) i originalni CNF (unutar svakog para), CPU pin, deterministički nasumični poredak modova, korektna evidencija usporenja i timeouta.
- Audit: SHA, SAT modeli, neovisna provjera svake nove GF(2) izvedene klauzule u samom mjerenju, regresije ≥2×, formula-level bootstrap, solved-count, ukupni i po-cohort PAR-2, detector time uključeno.
- Rezultati na poznatih 25 označavaju se samo kao **development** i ne predstavljaju opći proboj na novim formulama.

## Znanstveni kriterij nastavka

Prvi prolaz mora dokazati (1) da je nova izvedena klauzula logički implicirana iz izvornika, (2) da natjecateljski CDCL može potrošiti tu informaciju bez kršenja SAT ispravnosti, (3) da nema velikih regresija zbog detektora. Za ozbiljnu tvrdnju o proboju potreban je **novi** SHA-disjoint holdout, s naglaskom na `mixed_residual` i značajnije dulje limite (15 s / 60 s) uz isti budget i bez podešavanja prema holdoutu.

**Ne tvrditi "najjači na svijetu" na temelju poznatih 25 razvojnih formula.**

## Reference

- R154 prethodna SHA-fresh familijska validacija: https://github.com/Frane12/AndroidGameTest/actions/runs/42107642696
- R153 svi suparnici, 13 formulâ: https://github.com/Frane12/AndroidGameTest/actions/runs/42107076063
