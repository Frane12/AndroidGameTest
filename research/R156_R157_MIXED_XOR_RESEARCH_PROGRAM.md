# DRNAS SAT R156 → R157: mješoviti XOR–CNF istraživački program

Datum: 2026-11-05. Grana: `experiment/drnas-r156-residual-aware-xor-cdcl-20261105`.

## Precizan znanstveni problem

R153 rješava potpuno prepoznatljive XOR sustave i XOR + jedinične klauzule. R155 je već izvodio GF(2) posljedice na 4 mješovita originalna CNF-a, ali stariji benchmark je pri `subprocess.TimeoutExpired` odbacivao `stdout`, pa je pogrešno zapisivao `entailed_equation_trials=0`. Lokalni klasifikacijski test na SHA-originalima pokazao je 128/54/128/21 aktiviranih posljedica — nije dokaz ubrzanja. Prvi R156 CI smoke potvrđuje 97 rezidualno odabranih relacija u te četiri formule, s vremenom odluke 4.2/17.4/16.1/4.1 ms.

## Implementirano u R156

1. Iz originalnih 2–6 CNF parity obrazaca rekonstruira samo potpune XOR blokove; jedinice se prevode u točne GF(2) jednadžbe. Prije ikakvog zaključka GF(2) jednakost mora biti linearna posljedica tog izvornog sustava.
2. Izračunava važnost varijabli prema klauzulama koje nisu pokrivene dokazanim XOR blokovima (rezidualna CNF učestalost), a ne prema ukupnoj učestalosti.
3. Izvodi reducirane Gaussove redove i ograničeno sparivanje do 96 kraćih redova, za dodatne, još nepredstavljene GF(2) posljedice.
4. Odbacuje izvorne, već eksplicitne jednadžbe i identične kandidate. Rangira prema zahvaćenosti rezidualnog CNF-a, duljini i cijeni kodiranja.
5. Kratke posljedice (1–4 varijable) kodira izravno u CNF; dulje (5–12) preko Tseitin XOR lanca s egzistencijalnim pomoćnim varijablama.
6. Tvrde granice: 48 posljedica, 384 klauzule, 120 pomoćnih varijabli. Bez valjanih posljedica/prekoračeni troškovi → neizmijenjeni Kissat fallback.
7. Emitira `R156_SELECTION`, `R156_DERIVED_EQ`, `R156_ROUTE` s troškom. Novo mjerenje **čuva emitirani stdout nakon timeouta**, da ne ponovi krivu interpretaciju R155.

## Izvršen i aktivan test

- Smoke / 4 mixed SHA-originala: `https://github.com/Frane12/AndroidGameTest/actions/runs/42117843059` (kompilacija i aktivacijski test PASS).
- R156 development head-to-head: `https://github.com/Frane12/AndroidGameTest/actions/runs/42118586230`.
- 4 `mixed_residual` + 2 `complete_xor` + 2 `xor_plus_units` + 2 `nonxor_control` = 10 **prethodno viđenih** formula, 5 solvera (R156, R155, R153, Kissat, CryptoMiniSat), 2 ponavljanja, 15 s cap; 100 uparenih pokušaja.
- Usporedba istog SHA, ista hardverska grupa po formuli, SHA pin binarija, originalni SAT witness, reproducibilnost GF(2) linearnih posljedica neovisno iz izvornih CNF-a. Bez lažne tvrdnje da je development skup slijep.
- Audit mora odvojiti `route_activated`, `completed_augmented`, `timeout_activation_recovered`, PAR-2, solved, eq count, aux count i decision µs. Sva 4 sharda i 100 pokušaja obvezni.

## Stop/go kriteriji prije promocije

- Bez ijednog pogrešnog SAT odgovora ili neprovjerene ubrizgane GF(2) posljedice; dodatne pomoćne varijable ne smiju utjecati na izvorni model.
- UNSAT dobiven od vanjskog Kissata na proširenom modelu temelji se na ekvisatisfiabilnoj ekstenziji, ali **ne tvrditi formalni LRAT dokaz** ako ga nema.
- Ne proglašavati ubrzanje zbog samog izbora/aktivacije XOR posljedica. Potrebno stvarno smanjenje PAR-2 ili povećanje riješenih formula na `mixed_residual`, bez skrivanja brzinskih regresija.
- Ako 15 s test saturira timeoutovima, mjeriti 30–120 s, propagacije/konflikte kada solver to izvještava te odvojiti overhead izbora od efektivnosti rješavanja.
- Slijepi holdout **novih SHA-disjoint formula** treba zamrznuti prije vremenskih usporedbi; 20–100+ neviđenih iz različitih XOR/CNF obitelji, isti CPU/seed/limit. Osobito pratiti regresije >2×, bootstrapped paired 95 % interval i odnos prema CryptoMiniSatu.
- Stari R28, R153 i R155 ostaju neizmijenjeni i dostupni kao baseline. Bez automatske promocije.

## Sljedeći tehnološki korak R157 (ovisno o rezultatu R156)

Ako ponovno nema pomaka na mixed, preferirati izravni **in-process GF(2)–CDCL propagator** nad slanjem statičkih redundantnih klauzula: sinkronizacija CDCL traila, identifikacija XOR redova s jednom nedodijeljenom varijablom, povrat sigurnih propagacija i objašnjavajućih CNF reason klauzula, ograničeno ponovno ažuriranje GF(2) sustava, deterministički rollback na backtrack te mjerenje broja stvarnih novih propagacija, konflikata i CPU overhead-a. Koristiti već istraženi CaDiCaL/IPASIR-UP most kao polazište, ali prvo provjeriti dokumentirani API i zahtjeve za povratne reason/clauses. Provesti differential SAT/UNSAT testove i original-CNF proof replay prije širokog natjecateljskog benchmarka.
