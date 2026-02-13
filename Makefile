# Helper Makefile para desarrollo y automatización

APP_SVC ?= app
DB_SVC ?= db
DOCKER_COMPOSE ?= docker compose
MSG ?= update
REF ?= main
HEALTH_URL ?= http://localhost:8000/health

.PHONY: help up down down-v start stop restart ps logs shell rebuild rebuild-v push pull prune run backup restore deploy smoke

help:
	@echo "Comandos disponibles:"
	@echo "  make up        - Levanta los contenedores con build"
	@echo "  make down      - Detiene y elimina los contenedores"
	@echo "  make down-v    - Idem down, pero elimina también los volúmenes"
	@echo "  make restart   - Reinicia el contenedor principal"
	@echo "  make start     - Inicia el contenedor principal si está detenido"
	@echo "  make stop      - Detiene el contenedor principal"
	@echo "  make ps        - Lista contenedores activos"
	@echo ""
	@echo "Logs y shell:"
	@echo "  make logs      - Muestra logs de todos los contenedores"
	@echo "  make shell     - Abre una shell bash en el contenedor principal"
	@echo ""
	@echo "Rebuild:"
	@echo "  make rebuild   - Baja y vuelve a levantar los contenedores"
	@echo "  make rebuild-v - Idem rebuild, eliminando también volúmenes"
	@echo ""
	@echo "Git:"
	@echo "  make push MSG='msg' - Hace commit y push con mensaje"
	@echo "  make pull           - Hace pull desde main"
	@echo ""
	@echo "Utilidades:"
	@echo "  make prune    - Limpia recursos docker sin usar"
	@echo "  make run cmd  - Ejecuta un comando dentro del contenedor principal (ej: make run ls -la)"
	@echo ""
	@echo "Operación datos/deploy:"
	@echo "  make backup               - Genera dump lógico en ./backups"
	@echo "  make restore DUMP=...     - Restaura un dump en la base local"
	@echo "  make deploy DUMP=... REF=main - Hace restore + deploy con ref git"
	@echo "  make smoke                - Ejecuta smoke test contra /health"

# Contenedores
up:
	$(DOCKER_COMPOSE) up --build -d

down:
	$(DOCKER_COMPOSE) down

down-v:
	$(DOCKER_COMPOSE) down -v

start:
	$(DOCKER_COMPOSE) start $(APP_SVC)

stop:
	$(DOCKER_COMPOSE) stop $(APP_SVC)

restart:
	$(DOCKER_COMPOSE) restart $(APP_SVC)

ps:
	$(DOCKER_COMPOSE) ps

# Logs y shell
logs:
	-$(DOCKER_COMPOSE) logs -f || true

shell:
	$(DOCKER_COMPOSE) exec $(APP_SVC) /bin/bash

# Rebuild
rebuild:
	$(MAKE) down
	$(MAKE) up

rebuild-v:
	$(MAKE) down-v
	$(MAKE) up

# Git
push:
	git add .
	git commit -m "$(MSG)" || true
	git push

pull:
	git pull origin main

# Utilidades
prune:
	docker system prune

# Ejecutar comando dentro del contenedor
run:
	$(DOCKER_COMPOSE) exec $(APP_SVC) $(filter-out $@,$(MAKECMDGOALS))

backup:
	bash scripts/backup_db.sh

restore:
	@if [ -z "$(DUMP)" ]; then \
		echo "❌ Debes indicar DUMP=... (ruta al archivo .dump)"; \
		exit 1; \
	fi
	RESTORE_ONLY=1 bash scripts/restore_and_deploy.sh "$(DUMP)" "$(REF)"

deploy:
	@if [ -z "$(DUMP)" ]; then \
		echo "❌ Debes indicar DUMP=... (ruta al archivo .dump)"; \
		exit 1; \
	fi
	bash scripts/restore_and_deploy.sh "$(DUMP)" "$(REF)"

smoke:
	@echo "▶ Ejecutando smoke test en $(HEALTH_URL)"
	curl -fsS "$(HEALTH_URL)" >/dev/null && echo "✅ Smoke test OK"

# Target wildcard
%:
	@:
