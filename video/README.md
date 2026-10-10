# Vidéo motion design – Résidence Haut Standing, Riadh El Andalous

**Résultat :** [`output/riadh_el_andalous_ar.mp4`](output/riadh_el_andalous_ar.mp4)
1456×732 (même format que le rendu 3D), 30 i/s, ~86 s, voix off arabe + sous-titres arabes incrustés.
Les sous-titres existent aussi en fichier séparé : [`output/riadh_el_andalous_ar.srt`](output/riadh_el_andalous_ar.srt).

## Déroulé

| Scène | Voix off | Animation | Transition vers la suivante |
|---|---|---|---|
| Intro | فرصتك لامتلاك شقة راقية في رياض الأندلس | ouverture cinémascope sur ligne dorée, emblème (arc andalou), titre doré | balayage diagonal doré |
| Localisation | موقع مميّز – رياض الأندلس | épingle qui tombe sur le toit + ondes | zoom traversant |
| Haut standing | اكتشفوا إقامة من الطراز الرفيع… / تجمع بين الراحة، الأمان وجودة الحياة | badge « HAUT STANDING », 3 pictos (confort, sécurité, qualité de vie) | glissement (sens RTL) |
| Équipements | مميزات الإقامة + les 5 points | panneau avec pictos ; la caméra cadre chaque point (balcons, entrée, parking, « montée en ascenseur », façade) | scan bleu |
| Vente sur plan | البيع على المخطط / اختاروا شقتكم… / واستثمروا… | le bâtiment en **plan bleu**, un scan révèle le rendu réel, sélection d'un appartement « شقتكم » | iris depuis le portrait |
| Contact | للمزيد من المعلومات والحجز… + les 3 numéros | portrait, numéros tapés au rythme de la voix, ligne active surlignée | flash doré |
| Fin | استثمر في مستقبلك… | carte finale : logo, numéros, agence | fondu au noir |

Bande son : musique d'ambiance synthétisée (Ré majeur, 84 BPM), qui baisse automatiquement sous la voix et un peu plus pendant les numéros ; bruitages (whoosh, impacts, carillons, « ding » d'ascenseur, scan).

## Modifier / régénérer

```bash
./make.sh               # tout reconstruire (télécharge la voix + Whisper la 1re fois)
SKIP_TTS=1 ./make.sh    # garder la voix actuelle (vo/), refaire seulement image + son (~2 min)
python3 render.py --still 12.5 40   # aperçus PNG dans build/preview/
```

* **Texte parlé / sous-titres** : `script.json` (`tts` = texte vocalisé avec voyelles, `sub` = sous-titre affiché).
  Après modification, relancer `./make.sh` (sans `SKIP_TTS`).
* **Textes fixes** (nom de l'agence, numéros affichés, liste des équipements, appartement surligné) : `CONFIG` en haut de `render.py`.
* **Remplacer la voix de synthèse par une vraie voix** : déposer un fichier WAV par phrase dans `vo/cue_00.wav … cue_19.wav`,
  mettre à jour les durées dans `vo/timing.json`, puis `SKIP_TTS=1 ./make.sh` — tout le montage se recale automatiquement.

## Fichiers

* `script.json` – texte de la voix off et des sous-titres, phrase par phrase
* `tts.py` – synthèse vocale (Piper « ar_JO-kareem » via sherpa-onnx) ; plusieurs prises par phrase, Whisper garde la plus intelligible
* `timeline.py` – calage des scènes et transitions sur la voix
* `gfx.py` – texte arabe (shaping RAQM), dégradés dorés, pictos, emblème
* `render.py` – scènes, transitions, sous-titres, encodage H.264
* `audio.py` – musique, bruitages, mixage (−15 LUFS)
* `assets/` – rendu du bâtiment, portrait, polices (licence SIL OFL, voir `assets/fonts/licenses/`)

## À vérifier avant diffusion

* **Voix de synthèse** : modèle open source Piper `ar_JO-kareem-medium`. Sa licence d'origine n'est pas clairement documentée ;
  pour une publicité payante, une voix humaine (ou un service TTS sous licence commerciale) est plus sûre — voir ci-dessus pour la remplacer.
* **Nom d'agence** affiché sur la carte finale : « IMMOBILIÈRE WAHRA » (déduit du nom du dépôt) — à corriger dans `CONFIG` si besoin.
* Le portrait est accompagné de la mention « نحن في خدمتكم » (à votre service), sans nom.
