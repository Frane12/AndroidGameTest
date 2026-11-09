# DRNAS X24 — pratiti binarni graf, ne samo brojiti binarne klauzule

Eksperimentalna grana. Stabilni main, X22 i X23 ostaju netaknuti.

## Zašto novi smjer?

Visok postotak binarnih klauzula sam po sebi ne znači dokazive
ekvivalencije. Potrebno je pratiti smjer implikacija i povratne
putove, a ne samo stupanj binarnosti formule.

Izvorna klauzula (a ∨ b) daje bridove (¬a → b) i (¬b → a).
Nativni C++ scout gradi usmjereni graf potpisanih literala i prati
SCC na kontrolnim točkama nakon 25, 50, 75 i 100 posto klauzula.

Mjerimo broj bridova, broj SCC komponenti, broj SCC s više od jednog
literala, najveću SCC, broj potencijalnih potpisanih zamjena varijabli
i proturječne SCC u kojima su x i ¬x.

Izvorni Kissat pokreće se odmah na logičkom CPU-u A; C++ graf scout
promatra formulu na logičkom CPU-u B. Nakon izračuna grafa, CPU B
pokreće izvorni CaDiCaL ako je graf neobećavajući, ili zasebni
X22 C++ reducer pa CaDiCaL na reduciranom CNF-u.

## Sedam kontrolnih politika, unaprijed definirane

- kissat1: samostalni Kissat nad originalom.
- cadical1: samostalni CaDiCaL nad originalom.
- race_original: originalni Kissat i originalni CaDiCaL odmah.
- race_quotient: puni X22 reducer prije drugog solvera, bez SCC gatea.
- graph_shadow: trošak praćenja SCC grafa, zatim originalni CaDiCaL.
- graph_any: reduciraj ako je pronađena barem jedna potpisana zamjena
  kroz SCC; inače originalni CaDiCaL.
- graph_strict: reduciraj ako postoji barem 8 zamjena i (barem 32
  ukupno ili najmanje 0,5% broja varijabli); inače originalni CaDiCaL.

U slučaju proturječnih SCC (x i ¬x) ili neuspjelog čitača grafa
povratak je na originalni CaDiCaL. Takva komponenta može ukazivati na
UNSAT u binarnom dijelu, ali ne tvrdimo dokaz bez zasebnog certifikata.

## Ispravnost i ispitivanje

Graf je samo odabir strategije, nikad izvor neprovjerenih klauzula.
Neovisni X22 Python replayer za svaku predloženu zamjenu varijable
provjerava originalne implikacijske putove u oba smjera. SAT model
uvijek mora zadovoljiti nepromijenjeni izvorni CNF.

336 original-SHA uparenih E2E pokušaja, 24 ponovno korištene formule
iz X21/X22, 7 armova, 2 repeticije, 8 shardova i limit 15 s. Mjerimo
wall PAR2, CPU djece, broj riješenih SAT/UNSAT, biranje redukcije,
tok SCC pokazatelja kroz četiri checkpointa, trošak čitača i broj
stvarno rekonstruiranih aliasa.

Ovo nije novi slijepi holdout niti službeno SAT natjecanje. UNSAT se
prihvaća samo uz međusobno slaganje izvornih Kissat i CaDiCaL
na istom izvornom SHA. Slaganje dvaju solvera nije neovisni LRAT/FRAT
certifikat. Bez automatskog promoviranja na stable/main.
