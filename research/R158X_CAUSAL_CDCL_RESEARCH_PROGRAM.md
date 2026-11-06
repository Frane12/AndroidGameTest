# DRNAS R158x — uzročno mjerenje GF(2)–CDCL (6. studenoga 2026.)

Grana: experiment/drnas-r158x-causal-cdcl-gf2-20261106.

## Hipoteza i razlog

R153 je specijalizirano uspješan na potpunim XOR i XOR+unit formulama. R155–R157 pokazali su da otkrivanje XOR redova, dodavanje klauzula ili slanje GF(2) prijedloga ne daje nužno ubrzanje na mješovitim originalnim CNF-ovima. R157 je bilježio najmanje 1.876 prijedloga na osam neriješenih pokušaja, ali nije mogao izmjeriti stvarne CDCL konflikte i naučene klauzule na timeoutu.

R158x zato razdvaja opterećenje promatranja, odabir korisnih relacija i učinak na CDCL pretragu.

## Implementirano

- research/r158x_causal_cdcl_bridge.cpp: šest načina rada unutar iste CaDiCaL 2.1.0 binarije: clean, watch_boundary, shadow_boundary, direct_full, direct_boundary_nogate, direct_boundary.
- Shadow skenira i broji moguće XOR propagacije, ali ih ne vraća CDCL-u; time izdvaja trošak od koristi.
- Selektivni izbor certificiranih GF(2) jednadžbi: najviše 32, rangirano samo prema rezidualnim CNF klauzulama i raznolikosti varijabli. Puni R157 služi kao referenca.
- Konzervativna abstencija za selektivni direct način: nakon 100.000 skeniranih redova uz manje od tri izravna prijedloga prestaje dodavati nove vanjske propagacije. Ne mijenja izvorne klauzule ni ranije razloge.
- CaDiCaL Terminator vraća normalan UNKNOWN na isteku zadanog vremena, nakon čega solver.statistics() daje stvarne conflicts/decisions/learned/propagations. Nema uništavanja procesa prije očitanja.
- Nove metrike: završeni razlog-klauzula, broj doslovnih callbackova, shadow kandidati, direct prijedlozi, watch scans, conflicts, decisions, learned, propagations.
- Neovisno provjeravamo izvorne CNF SAT modele, izvorne GF(2) blokove i jedinične klauzule; UNSAT bez LRAT/FRAT ostaje bez neovisne potvrde.
- Jedna kompajlirana binarija distribuirana svim shardovima, čime se izbjegava R157 problem s različitim SHA-ovima.

## Test i pragovi

Skup: četiri poznate mješovite formule (15 s) te četiri originalne kontrole XOR/XOR+unit/ne-XOR (5 s). Šest metoda, dva ponavljanja = 96 uparenih pokušaja kroz četiri sharda. Isti CPU za svaku uparenu formulu, provjera originalnih SHA-ova. To je razvojni test već poznatih formula, nije blind holdout.

Ne proglasiti ubrzanje samo zbog većeg broja XOR propagacija ili manjeg broja konflikata kad oba solvera završe na timeoutu. Za napredak zahtijevati više riješenih formula ili potvrđeno niže vrijeme na rješivim mješovitim zadacima bez regresija. Nakon toga zamrznuti novu SHA-disjoint zbirku 20–100+ originalnih mješovitih formula i širu ne-XOR regresijsku zbirku.

GitHub run: https://github.com/Frane12/AndroidGameTest/actions/runs/42136262627
