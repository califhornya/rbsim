"""Which spec keys does each effect handler never read?

For every verb in effects.REGISTRY: the keys card specs give it (params +
target/scope/duration, the fields handlers receive) vs the string keys the
handler's source (and the helpers it calls) reads. Keys a spec sets but no code
reads are silently ignored: a card doing less (or more) than printed."""
import ast
import inspect
import re
import sys
from collections import defaultdict

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from riftbound.core import effects  # noqa: E402
from riftbound.core.effects import REGISTRY  # noqa: E402
from riftbound.registry.cards_registry import CARD_REGISTRY  # noqa: E402

src = inspect.getsource(effects)
tree = ast.parse(src)
funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def read_keys(fn_name, seen=None):
    """String keys read via .get("k") / ["k"] / "k" in, in fn and helpers it calls."""
    seen = seen or set()
    if fn_name in seen or fn_name not in funcs:
        return set()
    seen.add(fn_name)
    keys = set()
    for node in ast.walk(funcs[fn_name]):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                keys.add(node.args[0].value)
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
                and isinstance(node.slice.value, str):
            keys.add(node.slice.value)
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Constant) \
                and isinstance(node.left.value, str):
            keys.add(node.left.value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            keys |= read_keys(node.func.id, seen)
    return keys


# verb -> handler function name
handler_name = {verb: fn.__name__ for verb, fn in REGISTRY.items()}
# EffectContext methods the handlers call read their kwargs as parameters; treat
# target/scope as read when the handler passes them through.
ALWAYS = {"effect", "trigger", "timing", "condition", "cost", "additional_cost", "optional",
          "suggested_vocab"}

used = defaultdict(lambda: defaultdict(list))   # verb -> key -> [cards]
seen_cards = set()
for spec in CARD_REGISTRY.values():
    if spec.name in seen_cards:
        continue
    seen_cards.add(spec.name)
    for es in spec.effects:
        if es.trigger == "passive":
            continue      # folded by _apply_passive_grant, not the handler
        keys = set(es.params) | {k for k in ("target", "scope", "duration", "target_filter")
                                  if getattr(es, k) is not None}
        for k in keys:
            used[es.effect][k].append(spec.name)

for verb in sorted(used):
    if verb not in handler_name:
        continue
    reads = read_keys(handler_name[verb]) | ALWAYS
    if "target_filter" not in reads and "_resolve_targets" in inspect.getsource(REGISTRY[verb]):
        reads.add("target_filter")
    if "target" not in reads and "_resolve_targets" in inspect.getsource(REGISTRY[verb]):
        reads |= {"target", "scope"}
    ignored = {k: v for k, v in used[verb].items() if k not in reads}
    if ignored:
        print(f"{verb}:")
        for k, cards in sorted(ignored.items(), key=lambda kv: -len(kv[1])):
            print(f"    {k:22} {len(cards):3}  e.g. {', '.join(cards[:4])}")
