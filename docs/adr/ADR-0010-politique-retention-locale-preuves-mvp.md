# ADR-0010 : Politique de rétention locale des preuves pour le MVP

- **Date** : 2026-11-23
- **Statut** : acceptée

---

## Contexte

Les fichiers de preuves numériques (captures disques, images RAM) occupent des volumes considérables. L'entité `AuditEvent` est en mode ajout seul permanent (immuable) et l'entité `Case` peut transiter vers l'état `closed`.

La conservation indéfinie de ces volumétries pose des questions de saturation de l'espace disque sur l'hôte unique et de conformité avec les réglementations de protection des données (CDP, ARTCI).

---

## Décision

Nous retenons l'**Option A** :
1. Pour le périmètre strict du MVP, conservation locale indéfinie de l'ensemble des fichiers de preuves sur le volume persistant scellé, y compris après clôture du dossier (`status = 'closed'`).
2. Aucune routine de purge automatique n'est activée dans le MVP, afin d'éliminer tout risque de destruction accidentelle d'éléments de preuve susceptibles de faire l'objet de contre-expertises ou de réquisitions judiciaires.
3. Intégration d'un indicateur de capacité et de pourcentage d'utilisation de l'espace disque dans le point d'accès d'état de santé système `/api/v1/health` (alerte dès 85% d'occupation).
4. La politique d'archivage à froid compressé et de purge conforme post-clôture fera l'objet d'un module dédié en phase post-MVP.

---

## Conséquences

### Positives
- **Garantie probatoire absolue** : Préservation intégrale de la chaîne de conservation des preuves (*chain of custody*).
- **Simplicité technique** : Aucun risque d'incohérence entre les métadonnées en base et les fichiers réels.
- **Supervision proactive** : Alerte précoce sur la saturation de l'espace disque de stockage.

### Négatives / Risques
- Nécessite la vigilance de l'administrateur système pour libérer de l'espace disque si de multiples gros dossiers sont ingérés.

---

Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & AI/Tech Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-23
