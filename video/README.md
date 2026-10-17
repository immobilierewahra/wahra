# Vidéos motion design – Immobilière Wahra

## Résidence La Sirène R+6 – vidéo « trend » Tesla

**Résultat :** [`output/sirene_tesla.mp4`](output/sirene_tesla.mp4) — vertical 1080×1920, 19 s, voix off arabe motivante
+ sous-titres, musique (le beat « drop » au décollage) et bruitages.
La Tesla garée dans le rendu 3D ([`assets/sirene/residence.jpg`](assets/sirene/residence.jpg)) est détourée, s'allume
(réacteurs bleus sous les roues, jets de vapeur), décolle avec un réacteur arrière, monte la façade étage par étage
(compteur RDC → R+6, chaque étage s'illumine d'un balayage doré au passage, une note par étage sur le beat), fait un
**360° en l'air**, puis se pose sur le toit : l'enseigne « la Sirène » s'allume comme un néon, flash et confettis dorés.
Texte : « حتّى تسلا تنجّم زادة تطلع للسطح متاع Résidence La Sirène R+6 ».

| Temps | Voix off | Image |
|---|---|---|
| 0,4 s | حتّى تسلا الجديدة… اختارت عنوانها! | plan large, le titre tombe mot par mot |
| 4,0 s | لأنّ القمّة تستحقّ | décollage, fumée, compteur des étages |
| 6,1 s | طابقًا بعد طابق… | montée R+1 → R+6 |
| 7,8 s | طموح بلا حدود! | 360° en l'air |
| 10,6 s | إقامة La Sirène… هنا تبدأ القمّة! | atterrissage sur le toit, « وصلت للسطح! » |
| 14,0 s | عنوانك القادم… في الأعلى! | les 3 numéros apparaissent |
| 16,6 s | اتصلوا بنا الآن! | les numéros pulsent |

`python3 tesla.py` reconstruit tout (`sirene_plate.py` fait le détourage et reconstruit la rue derrière la voiture ;
`sirene_vo.py` génère la voix off dans `vo_sirene/` — voix de synthèse Piper « kareem », plusieurs prises par phrase,
Whisper garde la plus intelligible). Pour changer le texte : `LINES` dans `sirene_vo.py`, puis supprimer `vo_sirene/`
et relancer `python3 tesla.py` (les instants de chaque phrase sont dans `VO_AT` en haut de `tesla.py`).
Aucun logo Tesla n'est affiché (marque déposée) : seul le mot « تسلا » apparaît dans le texte.

## Yessine Centre – Radès (bureaux à vendre)

**Résultat :** [`output/yessine_centre_ar.mp4`](output/yessine_centre_ar.mp4) (+ [`.srt`](output/yessine_centre_ar.srt)) —
vidéo **verticale 1080×1440** (format 3:4 des photos), ~41 s, calée sur la voix off [`assets/yessine/voix_off.mp3`](assets/yessine/voix_off.mp3).

| Voix | Scène | Photo(s) |
|---|---|---|
| مكتبك ليس مجرد مكان للعمل، بل هو عنوان… | accroche dorée, logo Yessine Centre | `facade_grand_angle` |
| ياسين سنتر – رادس | « YESSINE CENTRE », épingle sur l'enseigne réelle, رادس · RADÈS | `facade_face` |
| مكاتب للبيع في موقع استراتيجي… | badge À VENDRE, pictos الراحة / قيمة الاستثمار | `facade_face2` (travelling vers le haut) |
| فضاء مهني… يليق بطموحاتك… انطلاقة مميزة… مكتبك القادم هنا | montage rapide, un mot-clé doré par photo | `hall_ascenseurs`, `couloir_marbre`, `espace_lumineux`, `grande_piece` |
| تواصلوا معنا… على الأرقام التالية | portrait + 3 numéros tapés à l'écran | fond flou `hall_boites` |
| واكتشفوا المكاتب المتاحة… عبر موقعنا الإلكتروني | galerie 4 photos, puce « رادس », carte « IMMOBILIÈRE WAHRA » | `bureau_vue`, `cuisine`, `sanitaire`, `couloir_int` |
| اختر لمشروعك عنواناً يليق بطموحك | slogan puis carte finale (logo, numéros, agence) | `facade_face` |

`./make.sh yessine` reconstruit tout (`script_yessine.json` : phrases, textes affichés, numéros ; `reel.py` : mise en scène).
Les photos retenues sont dans `assets/yessine/` (redressées et réduites) ; la photo retouchée par IA (enseignes déformées) a été écartée.

---

# Résidence Haut Standing, Riadh El Andalous

Trois versions, 1456×732 (même format que le rendu 3D), 30 i/s, voix off arabe + sous-titres arabes incrustés :

| Version | Vidéo | Sous-titres | Texte |
|---|---|---|---|
| **Votre voix off** (~46 s) | [`output/riadh_el_andalous_ar_voix.mp4`](output/riadh_el_andalous_ar_voix.mp4) | [`.srt`](output/riadh_el_andalous_ar_voix.srt) | [`script_voix.json`](script_voix.json) – montage calé sur l'enregistrement [`assets/voix_off.mp3`](assets/voix_off.mp3) |
| **30 secondes** | [`output/riadh_el_andalous_ar_30s.mp4`](output/riadh_el_andalous_ar_30s.mp4) | [`.srt`](output/riadh_el_andalous_ar_30s.srt) | [`script_30s.json`](script_30s.json) – texte condensé, seul le numéro principal est lu, les 2 WhatsApp sont affichés |
| Longue (~71 s) | [`output/riadh_el_andalous_ar.mp4`](output/riadh_el_andalous_ar.mp4) | [`.srt`](output/riadh_el_andalous_ar.srt) | [`script.json`](script.json) – le paragraphe complet |

La version « voix » garde l'enregistrement tel quel (aucune coupe ni accélération) : chaque phrase est repérée dans le fichier
(`src` = début/fin en secondes) et les animations se déclenchent sur les mots (`word_at`). Les numéros ne sont pas lus
(« اتصلوا بنا على الأرقام الظاهرة على الشاشة ») : ils s'affichent à ce moment-là.

La version 30 s dure exactement 30,0 s : si la voix ne tient pas, toutes les phrases sont accélérées du même facteur
(étirement temporel sans changer la hauteur de voix), dans la limite de ×1,35.

## Déroulé

| Scène | Voix off | Animation | Transition vers la suivante |
|---|---|---|---|
| Intro | فرصتك لامتلاك شقة راقية في رياض الأندلس | ouverture cinémascope sur ligne dorée, emblème (arc andalou), titre doré | balayage diagonal doré |
| Localisation | موقع مميّز – رياض الأندلس | épingle qui tombe sur le toit + ondes | zoom traversant |
| Haut standing | اكتشفوا إقامة من الطراز الرفيع… / تجمع بين الراحة، الأمان وجودة الحياة | badge « HAUT STANDING », 3 pictos (confort, sécurité, qualité de vie) | glissement (sens RTL) |
| Équipements | مميزات الإقامة + les 5 points | panneau avec pictos ; la caméra cadre chaque point (balcons, entrée, parking, « montée en ascenseur », façade) | scan bleu |
| Vente sur plan | *Vente sur plan* (voix française) / اختاروا شقتكم… / واستثمروا… | le bâtiment en **plan bleu**, un scan révèle le rendu réel, sélection d'un appartement « شقتكم » | iris depuis le portrait |
| Contact | للمزيد من المعلومات والحجز… + les 3 numéros | portrait, numéros tapés au rythme de la voix, ligne active surlignée | flash doré |
| Fin | استثمر في مستقبلك… | carte finale : logo, numéros, agence | fondu au noir |

Bande son : musique d'ambiance synthétisée (Ré majeur, 84 BPM), qui baisse automatiquement sous la voix et un peu plus pendant les numéros ; bruitages (whoosh, impacts, carillons, « ding » d'ascenseur, scan).

## Modifier / régénérer

```bash
./make.sh voix              # version sur votre voix off (assets/voix_off.mp3)
./make.sh 30s               # version 30 s (télécharge la voix + Whisper la 1re fois)
./make.sh                   # version longue
SKIP_TTS=1 ./make.sh 30s    # garder la voix actuelle (vo_30s/), refaire seulement image + son
VIDEO_VARIANT=30s python3 render.py --still 12.5 20   # aperçus PNG dans build/30s/preview/
```

### Voix ElevenLabs

`tts.py` sait utiliser ElevenLabs (modèle `eleven_multilingual_v2` : la même voix dit l'arabe et « Vente sur plan » en français).
Il faut, dans les réglages de l'environnement (menu de l'environnement cloud → *Edit*) :

1. **Network access** : autoriser le domaine `api.elevenlabs.io` ;
2. **Variables / secrets** : `ELEVENLABS_API_KEY` = votre clé API, et `ELEVENLABS_VOICE_ID` = l'ID de la voix choisie
   (par exemple une voix tunisienne/maghrébine de la *Voice Library* ElevenLabs ; sinon une voix multilingue par défaut est utilisée).

Ensuite `./make.sh 30s` utilise automatiquement ElevenLabs (vitesse 1,15, réglable via `settings.el_speed` dans le script).

* **Texte parlé / sous-titres** : `script.json` (`tts` = texte vocalisé avec voyelles, `sub` = sous-titre affiché).
  Après modification, relancer `./make.sh` (sans `SKIP_TTS`).
* **Textes fixes** (nom de l'agence, numéros affichés, liste des équipements, appartement surligné) : `CONFIG` en haut de `render.py`.
* **Nouvel enregistrement de voix** : remplacer `assets/voix_off.mp3`, mettre à jour dans `script_voix.json` le texte (`sub`)
  et la position de chaque phrase (`src`), puis `./make.sh voix` — tout le montage se recale automatiquement (`import_voice.py`).

## Fichiers

* `script.json` / `script_30s.json` – texte de chaque version ; `settings` (durée cible, vitesse…), `screen` (textes affichés)
* `tts.py` – voix off : ElevenLabs (si clé API) ou Piper hors-ligne (arabe « ar_JO-kareem », français « fr_FR-upmc » *Pierre*) ;
  plusieurs prises par phrase, Whisper garde celle qui reste la plus intelligible (y compris avec un fond musical simulé) ;
  ajustement automatique à la durée cible
* `import_voice.py` – découpe un enregistrement de voix off en phrases positionnées (version « voix »)
* `timeline.py` – calage des scènes et transitions sur la voix (choix de la version via `VIDEO_VARIANT`)
* `gfx.py` – texte arabe (shaping RAQM), dégradés dorés, pictos, emblème
* `render.py` – scènes, transitions, sous-titres, encodage H.264
* `audio.py` – musique, bruitages, mixage (−15 LUFS)
* `assets/` – rendu du bâtiment, portrait, polices (licence SIL OFL, voir `assets/fonts/licenses/`)

## À vérifier avant diffusion

* **Version « voix »** : utilise votre fichier `assets/voix_off.mp3` tel quel (les remarques de licence ci-dessous ne concernent que les versions synthétiques).
* **Voix de synthèse arabe** : modèle open source Piper `ar_JO-kareem-medium` (accent levantin). Sa licence d'origine n'est pas clairement documentée ;
  pour une publicité payante, une voix humaine (ou un service TTS sous licence commerciale) est plus sûre — voir ci-dessus pour la remplacer.
* **Voix française** (« Vente sur plan ») : UPMC *Pierre*, données sous licence CC BY-SA 4.0 (https://github.com/marytts/upmc-pierre-data) — mentionner l'attribution si exigé.
* **Voix tunisienne** : aucun modèle de voix tunisienne n'est téléchargeable depuis cet environnement. Solution : ElevenLabs (ci-dessus) avec une
  voix tunisienne de la Voice Library, ou les voix Microsoft `ar-TN-HediNeural` / `ar-TN-ReemNeural` (domaine `speech.platform.bing.com`).
* **Nom d'agence** affiché sur la carte finale : « IMMOBILIÈRE WAHRA » — confirmé par la voix off Yessine Centre.
* **Yessine Centre** : les numéros affichés sont ceux de l'annonce Riadh El Andalous (la voix ne les lit pas) ; l'adresse du site
  web n'étant pas connue, la carte « موقعنا الإلكتروني » affiche le nom de l'agence — à compléter dans `script_yessine.json` (`screen`).
* **La Sirène** : la voix off est la voix de synthèse `ar_JO-kareem` (même remarque de licence) ; les numéros affichés sont ceux
  de l'annonce Riadh El Andalous — à modifier dans `SCREEN` en haut de `tesla.py` si besoin.
* Le portrait est accompagné de la mention « نحن في خدمتكم » (à votre service), sans nom.
