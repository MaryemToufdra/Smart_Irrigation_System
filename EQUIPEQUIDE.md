# 1. Se positionner sur sa branche
git checkout nom-branche

# 2. Synchroniser avec la branche principale
git pull origin main

# 3. Développer et tester les fonctionnalités
# ... travail sur le code ...

# 4. Ajouter les changements
git add .

# 5. Créer un commit descriptif
git commit -m "description des changements"

# 6. Pousser les changements
git push origin nom-branche


# 7 Tester la connexion
python -c "from database.connection_p import test_connection; test_connection()"
# 8 Lancer la création complète de la base (migrations + seeders)
python scripts/setup_database.py                                                  EQUIPEQUIDE.md

