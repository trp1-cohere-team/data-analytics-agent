# Engagement Log

## Week 8 Public Evidence

### 2026-04-11 — Technical X Thread (Live)
- Thread URL: https://x.com/zimmskal/status/1908212073730875729
- Technical substance: discusses coding-agent benchmark setup, failure modes, and evaluation methodology.

### 2026-04-12 — Public Technical Reference Post
- URL: https://github.com/ucbepic/DataAgentBench
- Technical substance: benchmark structure, datasets, and evaluation expectations used by this project.

### 2026-04-13 — Public Context-Engineering Discussion
- URL: https://github.com/openai/agents.md/issues/11#issuecomment-3366858928
- Technical substance: context-file flattening and practical context-injection mechanics.
## Accessibility Check
- All links above are public and viewable without login.
# Signal Corps Engagement Log
## Team Cohere — TRP1 FDE Programme — Oracle Forge Weeks 8–9
---
## Daily Slack Posts

| Date | Channel Link | Notes |
|------|-------------|-------|
| 2026-04-08 | https://10academytrp1-vwm3694.slack.com/archives/C0AS4R16Y9E/p1775654325936649 | Week 8 Day 1 team update |
| 2026-04-09 | https://10academytrp1-vwm3694.slack.com/archives/C0ARSK8MT2N/p1775743456930219 | Week 8 Day 2 team update |
| 2026-04-10 | https://10academytrp1-vwm3694.slack.com/archives/C0ARSK8MT2N/p1775769592164119 | Week 8 Day 3 team update |
| 2026-04-13 | https://10academytrp1-vwm3694.slack.com/archives/C0ARSK8MT2N/p1776067072673979 | Week 8 Day 4 update — part 1 |
| 2026-04-13 | https://10academytrp1-vwm3694.slack.com/archives/C0ARSK8MT2N/p1776093543657739 | Week 8 Day 4 update — part 2 |
| 2026-04-13 | https://10academytrp1-vwm3694.slack.com/archives/C0ARSK8MT2N/p1776063986801489 | Week 8 Day 4 update — part 3 |
| 2026-04-14 | https://10academytrp1-vwm3694.slack.com/archives/C0ARSK8MT2N/p1776158314780339 | Week 8 Day 5 team update |
| 2026-04-15 | https://10academytrp1-vwm3694.slack.com/archives/C0ARSK8MT2N/p1776259985478869 | Week 9 Day 1 team update |
---
## Published Articles

| Date | Platform | Link | Title | Word Count |
|------|----------|------|-------|------------|
| 2026-04-15 | Medium | https://medium.com/@yohannesdereje1221/what-the-oracle-forge-taught-me-about-the-invisible-wall-between-ai-potential-and-production-5d4d5a018e81 | What the Oracle Forge Taught Me About the Invisible Wall Between AI Potential and Production Reality | ~1300 words |

---

## Social Media Posts

| Date | Platform | Link | Notes |
|------|----------|------|-------|
| 2026-04-14 | X (Twitter) | [paste your X intro post link here] | Team intro post — building data analytics agent, DAB 54.3% target |
| 2026-04-14 | LinkedIn | https://www.linkedin.com/posts/yohannes-dereje17_aiengineering-dataagents-buildinpublic-share-7449687123621879808-1DKu | Technical article — join key resolution story, production vs demo agents |
| 2026-04-15 | Medium | https://medium.com/@yohannesdereje1221/what-the-oracle-forge-taught-me-about-the-invisible-wall-between-ai-potential-and-production-5d4d5a018e81 | 1300-word technical article on context engineering and DAB benchmark |

---

## Community Participation Log

### Successful Engagements

| Date | Platform | Link | Topic |
|------|----------|------|-------|
| 2026-04-14 | Reddit r/MachineLearning | https://www.reddit.com/r/MachineLearning/comments/1la46eq/comment/og2vevj/ | Commented on enterprise data integration thread — join key resolution, DAB benchmark |
| 2026-04-14 | Reddit r/LocalLLaMA | https://www.reddit.com/r/LocalLLaMA/comments/1rv3yt3/comment/og2xeg4/ | Commented on AI agent database pattern thread — MCP Toolbox architecture, DuckDB limitation |

### Removed Posts and Comments

All posts below were automatically removed by Reddit spam filters due to new account status and low karma. Content is preserved below for resubmission in Week 9 once account karma is established.

| Date | Platform | Community | Status | Reason |
|------|----------|-----------|--------|--------|
| 2026-04-14 | Reddit | r/MachineLearning | Removed by moderators | New account spam filter triggered |
| 2026-04-14 | Reddit | r/LocalLLaMA | Removed by moderators | New account spam filter triggered |
| 2026-04-15 | Reddit | r/learnmachinelearning | Removed by moderators | New account spam filter triggered |
| 2026-04-15 | Reddit | r/ArtificialIntelligence | Blocked before posting | Post flair requirement — attempted but not published |

### Reposted Content

| Date | Platform | Community | Link | Notes |
|------|----------|-----------|------|-------|
| 2026-04-15 | Reddit | r/learnmachinelearning | https://www.reddit.com/r/learnmachinelearning/comments/1sm83hm/built_an_ai_agent_that_queries_postgresql_mongodb/ | Repost of removed r/LocalLLaMA content — also subsequently removed |

### Discord Attempts

| Date | Platform | Community | Status | Reason |
|------|----------|-----------|--------|--------|
| 2026-04-15 | Discord | Hugging Face server | Unable to join | Invite link discord.gg/huggingface not working at time of attempt |

---

## Resource Acquisition Report

| Resource | Date | Status | URL | Free Tier Limits |
|----------|------|--------|-----|-----------------|
| Cloudflare Workers | 2026-04-15 | Active | https://oracle-forge-sandbox.yohannesdereje1221.workers.dev/ | 100,000 requests/day, no credit card required |

### Cloudflare Workers Access Instructions for Team
- Worker URL: https://oracle-forge-sandbox.yohannesdereje1221.workers.dev/
- Set in team .env as: `SANDBOX_URL=https://oracle-forge-sandbox.yohannesdereje1221.workers.dev/`
- Account holder: Yohannes Dereje (yohannesdereje1221)
- Free tier: 100,000 requests/day, no credit card required
- To manage: workers.cloudflare.com
- Applied and activated: April 15, 2026

---

## Preserved Content for Week 9 Resubmission

### Post 1 — r/MachineLearning (Enterprise Data Integration Thread)
*Original comment removed. Content preserved for resubmission.*

This matches almost exactly what we're running into while building a data analytics agent against the UC Berkeley DataAgentBench benchmark this week.

Your second point about field definitions hit home. We're routing queries across PostgreSQL, MongoDB, SQLite, and DuckDB in the same session, and the join key problem alone has been a rabbit hole. Customer IDs are integers in one database and "CUST-00123" strings in another — same entity, completely different representation, no error thrown when you join them wrong. Just silent incorrect results.

What surprised us is that this isn't really a model problem. The LLM can generate perfect SQL. But if the agent doesn't first detect the format mismatch and resolve it before attempting the join, the answer is wrong every time.

The benchmark we're running against — DAB — was designed specifically because most benchmarks use clean single-table demos that hide all of this. The best model in the world currently scores 54.3% on it. The ceiling isn't model capability. It's context engineering around exactly the problems you're describing.

---

### Post 2 — r/LocalLLaMA (AI Agent Database Pattern Thread)
*Original comment removed. Content preserved for resubmission.*

We're running almost exactly this pattern right now while building a data analytics agent for the UC Berkeley DataAgentBench benchmark.

Our setup: the agent never touches the databases directly. All four database types — PostgreSQL, MongoDB, SQLite, and DuckDB — sit behind Google's MCP Toolbox running on port 5000. The agent calls tools like postgres_query, sqlite_query, and mongo_aggregate through the MCP protocol instead of raw database drivers. One tools.yaml file defines all connections and the agent calls from that.

A few things we've learned from this in practice:

The abstraction layer solves credential isolation cleanly — the agent has no idea what the connection strings look like. But it introduces a different problem: the agent now needs to know which tool to call for which question. When a query spans PostgreSQL and MongoDB in the same session, the routing logic becomes its own engineering challenge. We had to build a context layer that tells the agent what lives where before it even starts generating queries.

The other thing we haven't fully solved is the DuckDB case — it runs locally rather than through MCP because we couldn't get it working through the toolbox cleanly. So we ended up with three databases behind the API layer and one accessed directly, which is exactly the kind of inconsistency this pattern is meant to avoid.

Your point about audit logging is underrated. We're using query traces in our evaluation harness to score agent performance — every tool call gets logged with its result. That trace is actually more valuable than the final answer for debugging why an agent failed.

---

### Post 3 — r/learnmachinelearning
*Post removed. Content preserved for resubmission.*

**Title:** Built an AI agent that queries PostgreSQL + MongoDB simultaneously — here's the silent failure mode that almost broke everything

Learning ML in production is very different from learning ML in tutorials. This week our team found out the hard way.

We're building a data analytics agent that has to answer natural language questions across four database types simultaneously — PostgreSQL, MongoDB, SQLite, and DuckDB — as part of competing on the UC Berkeley DataAgentBench benchmark.

The benchmark was designed specifically because most ML benchmarks use clean, single-table demos that hide how messy real data actually is. The best AI model in the world currently scores 54.3% on it. We're trying to beat that.

Here's the failure mode that surprised us most: when our agent tried to join customer data between PostgreSQL and MongoDB, it returned zero rows. No error. No crash. Just empty results — and the agent confidently reported "no data found."

The actual problem? Customer IDs in PostgreSQL are integers (10293). The same customers in MongoDB are stored as strings with a prefix ("CUST-10293"). Standard database drivers can't match them. No syntax error is thrown. The agent just silently returns nothing.

We fixed it with a two-phase resolution approach. Full writeup: https://medium.com/@yohannesdereje1221/what-the-oracle-forge-taught-me-about-the-invisible-wall-between-ai-potential-and-production-5d4d5a018e81

---

## External Engagement Summary

### What was attempted
Signal Corps set up all four required platforms (X, LinkedIn, Reddit, Medium) and made substantive engagement attempts across all of them during Weeks 8 and 9.

### What succeeded
- LinkedIn technical article published on join key resolution and production AI engineering
- Medium 1300-word article published on context engineering and the DAB benchmark ceiling
- X intro post published targeting DAB 54.3% benchmark with @UCBEPIC tagged
- Cloudflare Workers free tier activated and worker deployed at oracle-forge-sandbox.yohannesdereje1221.workers.dev
- Daily Slack posts maintained across all working days

### What was blocked
- Reddit engagement was blocked by automated spam filters due to new account low karma status. All substantive content was prepared, posted, and preserved — removal was platform-side, not content-side. Content will be resubmitted in Week 9 as account karma builds.
- Discord Hugging Face server invite link was non-functional at time of attempt.

### Community intelligence gathered
The r/LocalLLaMA comment on the AI agent database pattern thread, before removal, validated our MCP Toolbox abstraction approach and surfaced a community discussion on hybrid local/remote database patterns. This was flagged to Intelligence Officers as relevant to KB v2 design decisions around DuckDB documentation.

---

*Last updated: April 15, 2026*
*Signal Corps: Yohannes Dereje & Addisu Taye*