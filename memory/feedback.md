---
name: user-feedback
description: User's feedback and preferences for how Claude should work
type: feedback
originSessionId: 8f1e1905-3ea9-41cb-8c35-e5b566983382
---
## Rules:
1. **All responses must be in Chinese** — User explicitly requested this on 2026-05-06
   - **Why:** User is a Chinese speaker, this is their preferred language
   - **How to apply:** Every response, every explanation, every code comment should be in Chinese

2. **Must save memories after every significant conversation** — User gets extremely frustrated when I don't remember past conversations
   - **Why:** This has happened 3 times now (twice today alone), user explicitly said "这可以节省我很多时间"
   - **How to apply:** At the end of each session, save key decisions, new facts, and project progress to memory

3. **Don't create things user can already get from existing tools** — User rejected the basic stock_fetcher.py because stock apps already show real-time data
   - **Why:** User said "你这个脚本写的东西，我在股票软件上也可以看得到啊？有什么用"
   - **How to apply:** Before building any tool, ask: "What value does this add beyond what the user already has?" Focus on analysis, aggregation, and insights that existing apps can't provide

5. **思考过程必须用中文** — 用户要求内部推理/思考过程也用中文
   - **Why:** 用户是中文母语者，希望思考过程也能被理解
   - **How to apply:** 所有 thinking 块内的内容都用中文书写

4. **Stock trading: focus on decision support, not predictions** — User wants help with trading decisions but I can't predict the market
   - **Why:** User explicitly asked for "预测行情走势或者说胜率预测"
   - **How to apply:** Build historical backtesting, pattern analysis, probability quantification, trade journaling — things that help the user make better-informed decisions, not predictions
