\set ON_ERROR_STOP on

SELECT 'CREATE DATABASE powa'
WHERE NOT EXISTS (
  SELECT 1
  FROM pg_database
  WHERE datname = 'powa'
)
\gexec

\connect powa

CREATE EXTENSION IF NOT EXISTS powa CASCADE;
