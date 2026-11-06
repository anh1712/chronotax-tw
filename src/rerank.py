"""C4 experiment: can a cross-encoder become time-aware with temporal hard negatives, or is a symbolic date filter needed?

Setup (no leakage): every article that appears in the TW-TaxTime `amount` test probes is EXCLUDED from training.
Training queries are synthetic cloze contexts cut from other article versions, with a date sampled inside that
version's validity interval. Inputs carry the dates as text:
    query   = "{as_of} {law} {context}"
    passage = "{valid_from}~{valid_to|今} {article} {window of the text around the best match}"
Negative mixes compared (same number of negatives per query):
    bm25     — top lexical hits from OTHER articles
    temporal — the superseded / later versions of the SAME article (only a versioned store can produce these)
    mixed    — half / half
Evaluation on the 264 amount probes, candidates = static FTS top-30 over ALL versions (date ignored), reranked by:
    bm25 order · zero-shot reranker · fine-tuned (each negative mix); plus the hybrid "date filter → rerank".
Metrics: R@1 of the gold version, misgrounding@1 (right article, wrong version), Wilson 95% CI.

  .venv/Scripts/python src/rerank.py data        # build train/test files
  .venv/Scripts/python src/rerank.py train MIX   # MIX in bm25|temporal|mixed  → data/models/rr-MIX
  .venv/Scripts/python src/rerank.py eval        # all systems → data/bench/results_rerank.json
"""
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "lawtw.db"
BENCH = ROOT / "data" / "bench"
MODELS = ROOT / "data" / "models"
BASE = "BAAI/bge-reranker-base"
N_NEG = 4
WIN = 220

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_retrieval import wilson  # noqa: E402


def db():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def window(text: str, ctx: str) -> str:
    """Text window around the first occurrence of the longest matching suffix of ctx (so the evidence is visible)."""
    for cut in range(len(ctx), 2, -1):
        i = text.find(ctx[-cut:])
        if i >= 0:
            s = max(0, i - WIN // 3)
            return text[s:s + WIN]
    return text[:WIN]


def passage(v, ctx: str) -> str:
    return f"{v['valid_from']}~{v['valid_to'] or '今'} {v['article_no']} {window(v['text'], ctx)}"


def query(as_of: str, law: str, ctx: str) -> str:
    return f"{as_of} {law} {ctx}"


def fts(con, law_id: str, ctx: str, k: int, extra: str = "", params: dict | None = None):
    return con.execute(
        "SELECT av.* FROM article_fts f JOIN article_version av ON av.id=f.rowid WHERE article_fts MATCH :q "
        f"AND av.law_id=:l AND av.deleted=0 {extra} ORDER BY bm25(article_fts) LIMIT :k",
        {"q": '"' + ctx.replace('"', "") + '"', "l": law_id, "k": k, **(params or {})}).fetchall()


def build_data(seed: int = 7, n_train: int = 6000) -> None:
    rng = random.Random(seed)
    con = db()
    names = {r["law_id"]: r["name"] for r in con.execute("SELECT law_id, name FROM law")}
    probes = [json.loads(l) for l in (BENCH / "tw_taxtime_v0.jsonl").open(encoding="utf-8")]
    probes = [t for t in probes if t["type"] in ("amount", "span")]
    # article-level split: all amount probes' articles plus a random 40% of the other articles are TEST articles;
    # training queries are cut only from the remaining articles (no article appears on both sides)
    arts = sorted({(t["law_id"], t["article"]) for t in probes})
    held = {(t["law_id"], t["article"]) for t in probes if t["type"] == "amount"}
    held |= set(rng.sample(arts, int(0.4 * len(arts))))
    test = [t for t in probes if (t["law_id"], t["article"]) in held]
    vs = [v for v in con.execute("SELECT * FROM article_version WHERE deleted=0 AND length(text)>=40 AND "
                                 "(valid_to IS NULL OR valid_to>valid_from)").fetchall()
          if (v["law_id"], v["article_no"]) not in held]
    by_art: dict = {}
    for v in vs:
        by_art.setdefault((v["law_id"], v["article_no"]), []).append(v)
    multi = [k for k, lst in by_art.items() if len(lst) >= 2]
    import datetime as dt
    train = []
    tries = 0
    while len(train) < n_train and tries < n_train * 5:
        tries += 1
        key = rng.choice(multi)  # articles with history, so temporal negatives exist
        v = rng.choice(by_art[key])
        t = v["text"].replace("\n", "")
        if len(t) < 40:
            continue
        i = rng.randrange(16, len(t) - 4)
        ctx = re.split(r"[，。；：、]", t[max(0, i - 24):i])[-1][-16:]
        if len(ctx) < 6:
            continue
        lo = dt.date.fromisoformat(v["valid_from"])
        hi = dt.date.fromisoformat(v["valid_to"]) if v["valid_to"] else dt.date(2026, 10, 1)
        if (hi - lo).days < 2:
            continue
        as_of = (lo + dt.timedelta(days=rng.randrange(1, (hi - lo).days))).isoformat()
        others = [o for o in by_art[key] if o["id"] != v["id"] and o["text"] != v["text"]]
        lex = [o for o in fts(con, v["law_id"], ctx, 20) if o["article_no"] != v["article_no"]]
        if not others or len(lex) < 2:
            continue
        train.append({"q": query(as_of, names[v["law_id"]], ctx), "pos": passage(v, ctx),
                      "neg_temporal": [passage(o, ctx) for o in rng.sample(others, min(N_NEG, len(others)))],
                      "neg_bm25": [passage(o, ctx) for o in lex[:N_NEG]]})
    with (BENCH / "rerank_train.jsonl").open("w", encoding="utf-8") as f:
        for r in train:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # test candidates: static FTS top-30 over ALL versions
    cands = []
    for t in test:
        rows = fts(con, t["law_id"], t["context"], 30)
        cands.append({"id": t["id"], "type": t["type"], "q": query(t["as_of"], t["law"], t["context"]), "as_of": t["as_of"],
                      "article": t["article"], "gold": t["gold_version_id"],
                      "cands": [{"id": r["id"], "article": r["article_no"], "valid_from": r["valid_from"],
                                 "valid_to": r["valid_to"], "p": passage(r, t["context"])} for r in rows]})
    with (BENCH / "rerank_test.jsonl").open("w", encoding="utf-8") as f:
        for r in cands:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    cov = sum(any(c["id"] == r["gold"] for c in r["cands"]) for r in cands) / len(cands)
    print(f"train {len(train)} queries (held-out articles excluded: {len(held)}), test {len(cands)}, "
          f"gold in static top-30: {cov:.3f}")


def train(mix: str, epochs: int = 1, bs: int = 16, lr: float = 2e-5) -> None:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    rng = random.Random(1)
    rows = [json.loads(l) for l in (BENCH / "rerank_train.jsonl").open(encoding="utf-8")]
    pairs = []
    for r in rows:
        if mix == "bm25":
            negs = r["neg_bm25"][:N_NEG]
        elif mix == "temporal":
            negs = (r["neg_temporal"] * N_NEG)[:N_NEG]
        else:
            negs = (r["neg_temporal"][: N_NEG // 2] + r["neg_bm25"])[:N_NEG]
        pairs.append((r["q"], r["pos"], 1.0))
        pairs += [(r["q"], n, 0.0) for n in negs]
    rng.shuffle(pairs)
    tok = AutoTokenizer.from_pretrained(BASE)
    model = AutoModelForSequenceClassification.from_pretrained(BASE, num_labels=1).cuda()
    # 8 GB laptop GPU shared with other processes: freeze the 250k-token embedding matrix (~2/3 of the parameters)
    # and use gradient checkpointing; the encoder layers and head are still fully trained.
    for prm in model.base_model.embeddings.parameters():
        prm.requires_grad = False
    model.gradient_checkpointing_enable()
    opt = torch.optim.AdamW([q for q in model.parameters() if q.requires_grad], lr=lr)
    steps = epochs * (len(pairs) + bs - 1) // bs
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / (0.1 * steps)) * max(0.0, 1 - s / steps))
    scaler = torch.amp.GradScaler()
    loss_fn = torch.nn.BCEWithLogitsLoss()
    model.train()
    step = 0
    for _ in range(epochs):
        for i in range(0, len(pairs), bs):
            b = pairs[i:i + bs]
            enc = tok([x[0] for x in b], [x[1] for x in b], truncation=True, max_length=320, padding=True,
                      return_tensors="pt").to("cuda")
            y = torch.tensor([x[2] for x in b], device="cuda")
            with torch.autocast("cuda", dtype=torch.float16):
                logits = model(**enc).logits.squeeze(-1)
            loss = loss_fn(logits.float(), y)
            opt.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            step += 1
            if step % 200 == 0:
                print(f"[{mix}] step {step}/{steps} loss {loss.item():.4f}", flush=True)
    out = MODELS / f"rr-{mix}"
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out)
    tok.save_pretrained(out)
    print("saved", out)


def score(model_dir: str, rows: list[dict]) -> list[list[float]]:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir).cuda().eval().half()
    out = []
    with torch.no_grad():
        for r in rows:
            if not r["cands"]:
                out.append([])
                continue
            enc = tok([r["q"]] * len(r["cands"]), [c["p"] for c in r["cands"]], truncation=True, max_length=320,
                      padding=True, return_tensors="pt").to("cuda")
            out.append(model(**enc).logits.squeeze(-1).float().tolist())
    return out


def metrics(rows, order_fn) -> dict:
    h1 = mis = 0
    hits = []
    for r in rows:
        ranked = order_fn(r)
        ok = bool(ranked) and ranked[0]["id"] == r["gold"]
        hits.append(ok)
        h1 += ok
        mis += bool(ranked) and ranked[0]["article"] == r["article"] and ranked[0]["id"] != r["gold"]
    n = len(rows)
    return {"n": n, "R@1": round(h1 / n, 3), "R@1_ci": wilson(h1, n), "misgrounding@1": round(mis / n, 3),
            "misgrounding@1_ci": wilson(mis, n), "_hits": hits}


def mcnemar(a: list[bool], b: list[bool]) -> dict:
    """Exact two-sided McNemar test on paired outcomes (same probes): b01 = only A right, b10 = only B right."""
    from math import comb
    b01 = sum(x and not y for x, y in zip(a, b))
    b10 = sum(y and not x for x, y in zip(a, b))
    n, k = b01 + b10, min(b01, b10)
    p = min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n) if n else 1.0
    return {"only_A": b01, "only_B": b10, "p": round(p, 4)}


def in_force(c, d):
    return c["valid_from"] <= d and (c["valid_to"] is None or c["valid_to"] > d)


def evaluate() -> None:
    rows = [json.loads(l) for l in (BENCH / "rerank_test.jsonl").open(encoding="utf-8")]
    res = {"bm25 (static)": metrics(rows, lambda r: r["cands"]),
           "date filter → bm25": metrics(rows, lambda r: [c for c in r["cands"] if in_force(c, r["as_of"])])}
    systems = {"zero-shot": BASE}
    for mix in ("bm25", "temporal", "mixed"):
        if (MODELS / f"rr-{mix}").exists():
            systems[f"fine-tuned/{mix}"] = str(MODELS / f"rr-{mix}")
    for name, path in systems.items():
        sc = score(path, rows)
        for r, s in zip(rows, sc):
            r["_s"] = s
        rank = lambda r: [c for _, c in sorted(zip(r["_s"], r["cands"]), key=lambda x: -x[0])]
        res[f"{name} (static)"] = metrics(rows, rank)
        res[f"date filter → {name}"] = metrics(rows, lambda r: [c for c in rank(r) if in_force(c, r["as_of"])])
    pairs = [("fine-tuned/temporal (static)", "fine-tuned/bm25 (static)"),
             ("fine-tuned/temporal (static)", "fine-tuned/mixed (static)"),
             ("fine-tuned/bm25 (static)", "zero-shot (static)"),
             ("date filter → fine-tuned/temporal", "date filter → bm25"),
             ("date filter → bm25", "fine-tuned/temporal (static)")]
    tests = {f"{a} vs {b}": mcnemar(res[a]["_hits"], res[b]["_hits"]) for a, b in pairs if a in res and b in res}
    by_type = {}
    for t in sorted({r.get("type", "amount") for r in rows}):
        sub = [r for r in rows if r.get("type", "amount") == t]
        by_type[t] = len(sub)
    out = {k: {kk: vv for kk, vv in v.items() if kk != "_hits"} for k, v in res.items()}
    out["_mcnemar"] = tests
    out["_test_by_type"] = by_type
    (BENCH / "results_rerank.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print("test probes by type:", by_type)
    for k, v in res.items():
        print(f"{k:34s} R@1={v['R@1']} {v['R@1_ci']}  misgrounding@1={v['misgrounding@1']} {v['misgrounding@1_ci']}")
    for k, v in tests.items():
        print(f"McNemar {k}: only A {v['only_A']}, only B {v['only_B']}, p={v['p']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1]
    if cmd == "data":
        build_data()
    elif cmd == "train":
        train(sys.argv[2])
    elif cmd == "eval":
        evaluate()
