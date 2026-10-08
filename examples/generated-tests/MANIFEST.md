# Generated test artifacts (examples/)

| File | Dataset | Description | SOC 2 controls |
|---|---|---|---|
| `test_schema_public_users.py` | `rm:postgres,public.users,PROD)` | Schema integrity test for public.users (postgres). Auto-generated from DataHub. | CC6.1, CC7.2 |
| `test_lineage_postgres_public_users_prod.py` | `rm:postgres,public.users,PROD)` | Lineage continuity test — verify upstream/downstream datasets map correctly. | CC6.1 |
| `test_owner_public_users.py` | `rm:postgres,public.users,PROD)` | Ownership completeness test — every dataset must have a DataHub owner. | CC6.1 |
| `test_schema_public_projects.py` | `postgres,public.projects,PROD)` | Schema integrity test for public.projects (postgres). Auto-generated from DataHub. | CC6.1, CC7.2 |
| `test_lineage_postgres_public_projects_prod.py` | `postgres,public.projects,PROD)` | Lineage continuity test — verify upstream/downstream datasets map correctly. | CC6.1 |
| `test_owner_public_projects.py` | `postgres,public.projects,PROD)` | Ownership completeness test — every dataset must have a DataHub owner. | CC6.1 |
