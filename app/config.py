"""Configuration de l'application."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional
from pathlib import Path

class Settings(BaseSettings):
    """Configuration de l'application.

    Note technique (21/07/2026) : `Field(env=...)` est un paramètre
    pydantic v1, silencieusement ignoré (et déprécié) en v2 -- il ne crée
    PAS l'alias qu'on pourrait croire. Les champs ci-dessous
    fonctionnaient malgré tout, par coïncidence : pydantic-settings fait
    correspondre un nom de champ à sa variable d'environnement du même
    nom, insensible à la casse, INDÉPENDAMMENT de ce paramètre (db_host
    correspond à DB_HOST tout seul, par exemple). Corrigé avec la
    syntaxe v2 (`validation_alias`), qui fonctionne vraiment -- utile
    dès qu'un nom de champ ne correspond pas telle quelle à sa variable
    d'environnement (ex: host/port -> APP_HOST/APP_PORT, pour ne pas
    entrer en collision avec un "PORT" générique que certains
    environnements définissent globalement).
    """

    # Écoute réseau du serveur (utilisé par `python app/main.py` -- voir
    # son bloc __main__. Sans effet sur un lancement `uvicorn app.main:app`
    # en ligne de commande : ce chemin-là exécute directement le module
    # importé, sans jamais passer par ce bloc, qui ne s'exécute QUE quand
    # le fichier est lancé en tant que script (`__name__ == "__main__"`).
    # Pour configurer host/port avec la commande uvicorn, ce sont ses
    # propres options --host/--port qui comptent, pas ces valeurs-ci.)
    host: str = Field(default="0.0.0.0", validation_alias="APP_HOST")
    port: int = Field(default=8000, validation_alias="APP_PORT")

    # Base de données SQLite (par défaut)
    db_host: str = Field(default="localhost", validation_alias="DB_HOST")
    db_port: int = Field(default=3306, validation_alias="DB_PORT")
    db_user: str = Field(default="root", validation_alias="DB_USER")
    db_password: str = Field(default="", validation_alias="DB_PASSWORD")
    db_name: str = Field(default="gestion_sources", validation_alias="DB_NAME")

    # LaraWeb
    laraweb_base_url: str = Field(
        default="http://www.lnhb.fr/Laraweb/Results/",
        validation_alias="LARAWEB_BASE_URL"
    )

    # Sécurité
    secret_key: str = Field(..., validation_alias="SECRET_KEY")
    algorithm: str = Field(default="HS256", validation_alias="ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
