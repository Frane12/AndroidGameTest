# DRNAS NP Lab v0.2 protiv CryptoMiniSata — reproducibilni benchmark

**Datum pripreme:** 31.10.2026.  
**Status:** lokalna verifikacija DRNAS-a izvršena. **NEMA** stvarnog CryptoMiniSat mjerenja u ovom okruženju: CryptoMiniSat nije instaliran i mrežno preuzimanje ovdje nije bilo dostupno. Svako CryptoMiniSat polje u priloženim lokalnim tablicama stoga je označeno `UNAVAILABLE`.

## Osnovna ideja

Na **identičnim DIMACS CNF datotekama** uspoređujemo DRNAS NP Lab v0.2 (Python) s **pravim** CryptoMiniSat CLI alatom (C++). Oba programa dobivaju jednake sirove CNF datoteke, bez metapodataka o tipu problema. Provjeravamo odgovor SAT/UNSAT i, kada je dostupan potpuni SAT model, neposredno provjeravamo svaku izvornu klauzulu.

Rezultati su vremenski **wall-clock** (uključuju pokretanje procesa), a ne čisto vrijeme matematičkog algoritma. Python ima različit startup overhead od C++. Stoga rezultate treba tumačiti kao *end-to-end* brzinu konkretnih implementacija, ne kao dokaz teorijske superiornosti.

## Struktura uzorka

Generator `generate_cases.py` deterministički stvara **34 instance**:

- Paritetni CNF: zadovoljen i proturječan (po tri veličine, dva sjemena), ukupno 12.
- Zamaskirani paritetni CNF, isto 12.
- Nasumični 3-SAT 24, 36, 48 varijabli, ukupno 6.
- Laki negativni kontrolni slučajevi (2-SAT i Horn), ukupno 4.

**Ograničenje:** većina instanci namjerno je sintetička i prilagođena našem strukturalnom eksperimentu. To **nije** neovisna SAT Competition evaluacija. CryptoMiniSat već podržava XOR i ima daleko razvijeniji mehanizam CDCL, stoga je realno očekivati da bude konkurentan ili brži.

## GitHub Actions: stvarna usporedba (preporučeno)

Priloženi `.github/workflows/compare-cryptominisat.yml` očekuje da je projekt kopiran u mapu `DRNAS_NP_Crypto_Benchmark/` unutar repozitorija, uz workflow YAML u **korijenskoj** `.github/workflows/` mapi repozitorija. Kad se workflow pokrene (ručno `workflow_dispatch` ili push), Ubuntu 24.04 runner:

1. Instalira službeni Ubuntu paket `cryptominisat` (u Ubuntu 24.04 trenutačno paket 5.11.15; nije nužno najnovija GitHub release verzija).
2. Validira DRNAS v0.2.
3. Generira identičnih 34 datoteka CNF.
4. Pokreće `benchmark_cryptominisat.py --crypto cryptominisat5 --timeout 2.0 --repeats 3 --require-crypto`.
5. Uploada `results/results.csv`, `results/summary.csv`, `results/environment.json` i ulazne CNF instance.

**`--require-crypto` jamči da zeleno izvršavanje nije lažni benchmark** — ako CryptoMiniSat ne postoji, workflow pada.

## Ručno pokretanje na Linuxu

```bash
sudo apt-get update
sudo apt-get install cryptominisat
cryptominisat5 --version
python3 generate_cases.py --dir cases --seeds 2
python3 drnas_np_lab.py test
python3 test_v02.py
python3 benchmark_cryptominisat.py --crypto cryptominisat5 --timeout 2 --repeats 3 --require-crypto
```

CSV izlaz se nalazi u `results/`. Podesi `--timeout 10` ako previše težih slučajeva završava `TIMEOUT`. Na istom računalu ponovi serije kako bi smanjio šum mjerenja.

## Kontrola ispravnosti

- DRNAS v0.2 koristi isti kod kao u našem prethodnom v0.2 prototipu, bez namjerne promjene samog solvera.
- `test_v02.py` dodatno provjerava ekvivalentnost i SAT/UNSAT odgovore na malim instancama iscrpnim pretraživanjem.
- Generirane paritetne SAT/UNSAT instance imaju matematički poznat status. Random 3-SAT nije unaprijed označen kao SAT ili UNSAT.
- SAT model je označen `OK` samo ako sadrži vrijednosti svih varijabli i stvarno zadovoljava izvornu CNF formulu. Ako CryptoMiniSat iz nekog razloga ne ispiše model, označava se `MODEL_NOT_EMITTED`; to nije isto što i provjera modela.
- `UNSAT` bez formalnog dokaza nije neovisno strojno dokazani UNSAT; može se naknadno dodati provjera dokaza (XLRUP/FRAT) iz CryptoMiniSat sustava.
- Timeout (`TIMEOUT`, `LIMIT`) ne znači UNSAT.

## Sadržaj

- `drnas_np_lab.py`, `drnas_cli.py`: DRNAS rješavač i pojedinačni SAT CLI pokretač.
- `generate_cases.py`: deterministički generator.
- `benchmark_cryptominisat.py`: neovisni proces za svaki test i solver.
- `experiment_v02.py`, `experiment_masked.py`: prethodni generatori.
- `cases/`: svi primjeri i `manifest.csv`, s fiksnim sjemenima.
- `results/`: lokalna DRNAS mjerenja; CryptoMiniSat = `UNAVAILABLE`.
- `.github/workflows/compare-cryptominisat.yml`: automatizirani **stvarni** test za GitHub Actions.

**Odvojiti budući rezultat od postojećeg:** U ovoj isporuci nema stvarno izmjerene brojke CryptoMiniSata. Rezultat koji bi se mogao javno citirati zahtijeva uspješno pokretanje pravog CryptoMiniSat binerija na istim instancama i očuvane CSV zapise.