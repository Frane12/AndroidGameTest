# Razvojna referenca: X5_NO_MIN

Korisnik je 13. 11. 2026. odabrao **X5_NO_MIN** kao referencu za daljnji razvoj DRNAS-a. Sve nove varijante uspoređuju se s tom zamrznutom konfiguracijom; CORE ostaje povijesna kontrola, a Kissat, CaDiCaL i CryptoMiniSat vanjske reference.

Točan identitet i postavke zapisani su u [baseline.json](baseline.json): `build/drnas-x5`, `--mode core --x5-no-minimize`, bez globalne memorije, cachea i periodične dijagnostike. Standardni izlaz statistike, SAT modela i UNSAT dokaza ostaje dio benchmarka. Koristi se jedan logički CPU i uparena usporedba istih formula uz jednak E2E limit i neovisnu provjeru.

Potvrđeni FAMILY15 rezultat: X5_NO_MIN 8/150 verificiranih pokušaja, ukupni PAR2 4274.113405274 s; CORE 6/150, 4320.597127695 s. Skup sadrži 75 originalnih SAT2024 formula, dva ponavljanja i limit 15 s. [Završni run](https://github.com/Frane12/AndroidGameTest/actions/runs/43392230840).

Odabir razvojne reference nije tvrdnja o pobjedi nad vanjskim solverima. Kandidat za njezinu zamjenu treba najmanje 10% niži verificirani PAR2 na novom uparenom holdoutu, pozitivan donji interval pouzdanosti grupiran po izvornoj formuli, bez pogrešnih rezultata i bez regresije broja riješenih pokušaja po obitelji. Globalna memorija i cache mjere se kao zasebne varijante prema ovoj osnovi.

Ova odluka vrijedi za buduće usporedbe; povijesni protokoli i postojeći rezultati zadržavaju svoje izvorne oznake i kontrole.
