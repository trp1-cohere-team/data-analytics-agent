## to start mcp , duckdb bridge custome mcp, sadnbox, mongodb and  postgres

sudo docker compose -f docker-compose.yml up -d

## to check

sudo docker compose -f docker-compose.yml ps
## to stop 
sudo docker compose -f docker-compose.yml down
## questions
python3 -m agent.data_agent.cli "YOUR QUESTION" \
  --db-hints '["postgresql", "sqlite", "duckdb", "mongodb"]