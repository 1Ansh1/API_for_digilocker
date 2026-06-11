# Diff Details

Date : 2026-06-09 16:08:07

Directory c:\\Users\\Asus\\Documents\\Digi_API\\app

Total : 82 files,  1977 codes, 910 comments, 449 blanks, all 3336 lines

[Summary](results.md) / [Details](details.md) / [Diff Summary](diff.md) / Diff Details

## Files
| filename | language | code | comment | blank | total |
| :--- | :--- | ---: | ---: | ---: | ---: |
| [app/\_\_init\_\_.py](/app/__init__.py) | Python | 1 | 1 | 2 | 4 |
| [app/api/\_\_init\_\_.py](/app/api/__init__.py) | Python | 0 | 1 | 1 | 2 |
| [app/api/deps.py](/app/api/deps.py) | Python | 84 | 22 | 23 | 129 |
| [app/api/v1/\_\_init\_\_.py](/app/api/v1/__init__.py) | Python | 0 | 1 | 1 | 2 |
| [app/api/v1/callback.py](/app/api/v1/callback.py) | Python | 125 | 9 | 18 | 152 |
| [app/api/v1/health.py](/app/api/v1/health.py) | Python | 66 | 26 | 33 | 125 |
| [app/api/v1/router.py](/app/api/v1/router.py) | Python | 17 | 11 | 8 | 36 |
| [app/api/v1/verification.py](/app/api/v1/verification.py) | Python | 84 | 8 | 15 | 107 |
| [app/config.py](/app/config.py) | Python | 144 | 44 | 55 | 243 |
| [app/errors/\_\_init\_\_.py](/app/errors/__init__.py) | Python | 0 | 4 | 1 | 5 |
| [app/errors/codes.py](/app/errors/codes.py) | Python | 41 | 14 | 12 | 67 |
| [app/errors/exceptions.py](/app/errors/exceptions.py) | Python | 83 | 25 | 50 | 158 |
| [app/errors/handlers.py](/app/errors/handlers.py) | Python | 81 | 21 | 23 | 125 |
| [app/infrastructure/\_\_init\_\_.py](/app/infrastructure/__init__.py) | Python | 12 | 4 | 5 | 21 |
| [app/infrastructure/database.py](/app/infrastructure/database.py) | Python | 27 | 42 | 10 | 79 |
| [app/infrastructure/digilocker/\_\_init\_\_.py](/app/infrastructure/digilocker/__init__.py) | Python | 10 | 4 | 3 | 17 |
| [app/infrastructure/digilocker/client.py](/app/infrastructure/digilocker/client.py) | Python | 14 | 38 | 10 | 62 |
| [app/infrastructure/digilocker/interface.py](/app/infrastructure/digilocker/interface.py) | Python | 13 | 60 | 8 | 81 |
| [app/infrastructure/digilocker/mock.py](/app/infrastructure/digilocker/mock.py) | Python | 150 | 38 | 30 | 218 |
| [app/infrastructure/digilocker/stub.py](/app/infrastructure/digilocker/stub.py) | Python | 54 | 41 | 14 | 109 |
| [app/infrastructure/http\_client.py](/app/infrastructure/http_client.py) | Python | 29 | 27 | 15 | 71 |
| [app/infrastructure/redis.py](/app/infrastructure/redis.py) | Python | 36 | 37 | 18 | 91 |
| [app/main.py](/app/main.py) | Python | 91 | 37 | 31 | 159 |
| [app/middleware/\_\_init\_\_.py](/app/middleware/__init__.py) | Python | 0 | 1 | 1 | 2 |
| [app/middleware/auth.py](/app/middleware/auth.py) | Python | 0 | 7 | 1 | 8 |
| [app/middleware/logging.py](/app/middleware/logging.py) | Python | 31 | 12 | 12 | 55 |
| [app/middleware/rate\_limit.py](/app/middleware/rate_limit.py) | Python | 0 | 7 | 1 | 8 |
| [app/middleware/request\_id.py](/app/middleware/request_id.py) | Python | 18 | 16 | 9 | 43 |
| [app/models/\_\_init\_\_.py](/app/models/__init__.py) | Python | 5 | 1 | 4 | 10 |
| [app/models/audit\_event.py](/app/models/audit_event.py) | Python | 74 | 5 | 15 | 94 |
| [app/models/base.py](/app/models/base.py) | Python | 15 | 3 | 9 | 27 |
| [app/models/verification.py](/app/models/verification.py) | Python | 70 | 5 | 17 | 92 |
| [app/models/verification\_result.py](/app/models/verification_result.py) | Python | 49 | 4 | 12 | 65 |
| [app/observability/\_\_init\_\_.py](/app/observability/__init__.py) | Python | 0 | 4 | 1 | 5 |
| [app/observability/logging.py](/app/observability/logging.py) | Python | 76 | 34 | 20 | 130 |
| [app/observability/metrics.py](/app/observability/metrics.py) | Python | 78 | 26 | 21 | 125 |
| [app/observability/tracing.py](/app/observability/tracing.py) | Python | 29 | 35 | 14 | 78 |
| [app/repositories/\_\_init\_\_.py](/app/repositories/__init__.py) | Python | 4 | 1 | 3 | 8 |
| [app/repositories/audit.py](/app/repositories/audit.py) | Python | 30 | 19 | 8 | 57 |
| [app/repositories/verification.py](/app/repositories/verification.py) | Python | 24 | 31 | 10 | 65 |
| [app/repositories/verification\_result.py](/app/repositories/verification_result.py) | Python | 43 | 35 | 10 | 88 |
| [app/schemas/\_\_init\_\_.py](/app/schemas/__init__.py) | Python | 0 | 1 | 1 | 2 |
| [app/schemas/callback.py](/app/schemas/callback.py) | Python | 6 | 2 | 6 | 14 |
| [app/schemas/errors.py](/app/schemas/errors.py) | Python | 9 | 3 | 8 | 20 |
| [app/schemas/health.py](/app/schemas/health.py) | Python | 6 | 3 | 8 | 17 |
| [app/schemas/provider.py](/app/schemas/provider.py) | Python | 16 | 10 | 9 | 35 |
| [app/schemas/verification.py](/app/schemas/verification.py) | Python | 15 | 4 | 13 | 32 |
| [app/security/\_\_init\_\_.py](/app/security/__init__.py) | Python | 0 | 1 | 1 | 2 |
| [app/security/hashing.py](/app/security/hashing.py) | Python | 16 | 41 | 8 | 65 |
| [app/security/jwt\_utils.py](/app/security/jwt_utils.py) | Python | 0 | 10 | 1 | 11 |
| [app/security/pkce.py](/app/security/pkce.py) | Python | 10 | 22 | 8 | 40 |
| [app/security/rate\_limit.py](/app/security/rate_limit.py) | Python | 62 | 27 | 17 | 106 |
| [app/security/state.py](/app/security/state.py) | Python | 6 | 14 | 8 | 28 |
| [app/services/\_\_init\_\_.py](/app/services/__init__.py) | Python | 0 | 1 | 1 | 2 |
| [app/services/jwks.py](/app/services/jwks.py) | Python | 60 | 31 | 18 | 109 |
| [app/services/oauth.py](/app/services/oauth.py) | Python | 27 | 28 | 10 | 65 |
| [app/services/token.py](/app/services/token.py) | Python | 50 | 34 | 17 | 101 |
| [app/services/verification.py](/app/services/verification.py) | Python | 426 | 125 | 64 | 615 |
| [app/static/css/style.css](/app/static/css/style.css) | PostCSS | 485 | 16 | 87 | 588 |
| [app/templates/architecture.html](/app/templates/architecture.html) | HTML | 93 | 0 | 9 | 102 |
| [app/templates/base.html](/app/templates/base.html) | HTML | 34 | 4 | 4 | 42 |
| [app/templates/dashboard.html](/app/templates/dashboard.html) | HTML | 79 | 3 | 12 | 94 |
| [app/templates/home.html](/app/templates/home.html) | HTML | 58 | 0 | 8 | 66 |
| [app/templates/mock\_provider.html](/app/templates/mock_provider.html) | HTML | 82 | 8 | 12 | 102 |
| [app/templates/result.html](/app/templates/result.html) | HTML | 133 | 3 | 12 | 148 |
| [app/templates/start.html](/app/templates/start.html) | HTML | 45 | 0 | 8 | 53 |
| [app/templates/timeline.html](/app/templates/timeline.html) | HTML | 135 | 2 | 13 | 150 |
| [app/ui/router.py](/app/ui/router.py) | Python | 234 | 30 | 42 | 306 |
| [tests/\_\_init\_\_.py](/tests/__init__.py) | Python | 0 | -1 | -1 | -2 |
| [tests/conftest.py](/tests/conftest.py) | Python | -49 | -19 | -24 | -92 |
| [tests/integration/\_\_init\_\_.py](/tests/integration/__init__.py) | Python | 0 | -1 | -1 | -2 |
| [tests/mock\_provider/\_\_init\_\_.py](/tests/mock_provider/__init__.py) | Python | 0 | -1 | -1 | -2 |
| [tests/unit/\_\_init\_\_.py](/tests/unit/__init__.py) | Python | 0 | -1 | -1 | -2 |
| [tests/unit/test\_deps.py](/tests/unit/test_deps.py) | Python | -130 | -17 | -48 | -195 |
| [tests/unit/test\_health.py](/tests/unit/test_health.py) | Python | -15 | -7 | -7 | -29 |
| [tests/unit/test\_persistence.py](/tests/unit/test_persistence.py) | Python | -226 | -35 | -54 | -315 |
| [tests/unit/test\_provider.py](/tests/unit/test_provider.py) | Python | -148 | -25 | -50 | -223 |
| [tests/unit/test\_rate\_limit.py](/tests/unit/test_rate_limit.py) | Python | -89 | -14 | -23 | -126 |
| [tests/unit/test\_security.py](/tests/unit/test_security.py) | Python | -41 | -13 | -22 | -76 |
| [tests/unit/test\_services.py](/tests/unit/test_services.py) | Python | -221 | -46 | -69 | -336 |
| [tests/unit/test\_ui.py](/tests/unit/test_ui.py) | Python | -132 | -12 | -34 | -178 |
| [tests/unit/test\_verification.py](/tests/unit/test_verification.py) | Python | -767 | -82 | -175 | -1,024 |

[Summary](results.md) / [Details](details.md) / [Diff Summary](diff.md) / Diff Details