# DRNAS X25 — native signed-SCC alias dose ablation (64 / 128 / 256 / 512)

## Istraživačko pitanje

X23G otkrio je uzorkom 328 i 89 potencijalnih zamjena na nekim
izvornim SHA formulama, a X22 nativni reducer ograničio se na 64.
Testiramo *uzročni učinak kapaciteta zamjena* u inače identičnom
nativnom signed-SCC quotient algoritmu.

## Pre-registrirani benchmark

24 izvorne SHA formule iz X21/X22, 2 ponavljanja, 7 armova, 8
paralelnih shardova i 15 s strogi wall E2E limit: 336 mjerenja.

- kissat1 (kontrola, jedan CPU)
- cadical1 (kontrola, jedan CPU)
- race_original (Kissat + CaDiCaL odmah)
- cap64 (C++ signed SCC reducer, najviše 64 zamjene)
- cap128 (isti algoritam, najviše 128)
- cap256 (isti algoritam, najviše 256)
- cap512 (isti algoritam, najviše 512)

Logički CPU 0 nastavlja izvornog Kissata. Na CPU 1 radi C++ reducer,
neovisna provjera izvornog implikacijskog grafa, pa CaDiCaL na
transformiranoj CNF. Sat vremena pretraživanja nije mjerilo:
uspoređuje se E2E wall vrijeme unutar 15 sekundi i ukupni child CPU.
Svi SHA, seedovi i 15-sekundni limiti upareni su po izvoru i rep.

## Provjere prije pokretanja

1. Sintetska CNF formula s 599 ekvivalentnih varijabli: primijenjenih
   64, 128, 256, 512 i prijavljenih 599 dostupnih zamjena.
2. Mnoštvo malih iscrpno testiranih SAT/UNSAT formula za svaki limit:
   očuvanje zadovoljivosti i originalnih podignutih SAT svjedoka.
3. Native cap64 mora proizvoditi byte-identical reduced.cnf i alias.map
   kao zamrznuti X22 na četiri originalne SHA formule.
4. Provjera izvornog binarnog implikacijskog grafa u Pythonu:
   uzajamna doseživost pomoću neovisno ponovno izračunanih SCC-ova,
   uključujući potpisane negacije. To je ekvivalent X22 BFS provjeri.
5. Svaki prijavljeni SAT svjedok validira se nad originalnom CNF.
   UNSAT je prihvaćen samo uz izvorni Kissat i CaDiCaL konsenzus,
   uključujući prethodno zamrznutu X22 evidenciju. Konsenzus NIJE
   neovisni LRAT/FRAT certifikat.

## Mjerila

Po armu: PAR2 u sekundama, prihvaćeni SAT/UNSAT, relativni %
prema race_original, CPU sekunde, broj stvarno rekonstruiranih
zamjena, broj odstranjenih klauzula, pomoćna i provjerna režija.
Posebno analizirati grupu izvornih SHA s više od 64 matematički
moguće zamjene. No auto promotion; ovo je replay, ne blind holdout.

Stabilni main i zamrznuti X22/X23/X23G/X24 ostaju netaknuti.
