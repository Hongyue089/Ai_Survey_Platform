"""A bounded Python subset for Flow calculations, executed in a separate process."""
import ast
import json
import operator
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import BoundedSemaphore

LIMIT = 32_768
WORKERS = BoundedSemaphore(4)
REFERENCES = re.compile(r"\{#([A-Za-z0-9_-]+)#\}")
BINARY = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
}
COMPARE = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Gt: operator.gt,
    ast.GtE: operator.ge, ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.In: lambda left, right: left in right, ast.NotIn: lambda left, right: left not in right,
}
FUNCTIONS = {"len": len, "min": min, "max": max, "sum": sum, "int": int,
             "float": float, "str": str, "bool": bool, "abs": abs, "round": round}


def run_python(code, answers):
    payload = json.dumps({"code": code, "answers": answers}, ensure_ascii=True)
    if len(payload) > LIMIT * 4:
        return {"error": "ValueError", "message": "Python input exceeds the size limit"}
    if not WORKERS.acquire(blocking=False):
        return {"error": "RuntimeError", "message": "Python workers are busy. Please retry."}
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-S", str(Path(__file__).resolve())],
            input=payload, capture_output=True, encoding="utf-8", timeout=2, check=True,
            env={name: os.environ[name] for name in ("SystemRoot", "WINDIR") if name in os.environ},
        )
        return json.loads(completed.stdout)
    except subprocess.TimeoutExpired:
        return {"error": "TimeoutError", "message": "The calculation exceeded two seconds"}
    except (OSError, subprocess.CalledProcessError, ValueError):
        return {"error": "RuntimeError", "message": "The Python worker could not complete the calculation"}
    finally:
        WORKERS.release()


class Calculation:
    def __init__(self, answers):
        self.values = {"response": answers, "result": {}}
        self.steps = 0
        self.line = None

    def step(self, node):
        self.steps += 1
        if self.steps > 500:
            raise ValueError("Calculation exceeds the operation limit")
        self.line = getattr(node, "lineno", self.line)

    @staticmethod
    def bounded(value):
        if len(json.dumps(value, ensure_ascii=True, allow_nan=False)) > LIMIT:
            raise ValueError("Calculation value exceeds the size limit")
        return value

    def expression(self, node):
        self.step(node)
        if isinstance(node, ast.Constant) and type(node.value) in (str, int, float, bool, type(None)):
            return node.value
        if isinstance(node, ast.Name):
            return self.values[node.id]
        if isinstance(node, (ast.List, ast.Tuple)):
            return self.bounded([self.expression(item) for item in node.elts])
        if isinstance(node, ast.Dict) and all(key is not None for key in node.keys):
            return self.bounded({self.expression(key): self.expression(value)
                                 for key, value in zip(node.keys, node.values)})
        if isinstance(node, ast.Subscript):
            return self.expression(node.value)[self.expression(node.slice)]
        if isinstance(node, ast.BinOp) and type(node.op) in BINARY:
            left, right = self.expression(node.left), self.expression(node.right)
            if isinstance(node.op, ast.Mult) and not all(type(value) in (int, float) for value in (left, right)):
                raise ValueError("Multiplication is supported for numbers only")
            if isinstance(node.op, ast.Mod) and not all(type(value) in (int, float) for value in (left, right)):
                raise ValueError("Remainder is supported for numbers only")
            return self.bounded(BINARY[type(node.op)](left, right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.Not, ast.USub, ast.UAdd)):
            value = self.expression(node.operand)
            return not value if isinstance(node.op, ast.Not) else -value if isinstance(node.op, ast.USub) else +value
        if isinstance(node, ast.BoolOp):
            value = self.expression(node.values[0])
            for item in node.values[1:]:
                if bool(value) == isinstance(node.op, ast.Or):
                    break
                value = self.expression(item)
            return value
        if isinstance(node, ast.Compare):
            left = self.expression(node.left)
            for op, other in zip(node.ops, node.comparators):
                right = self.expression(other)
                if not COMPARE[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            return self.expression(node.body if self.expression(node.test) else node.orelse)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in FUNCTIONS and not node.keywords):
            args = [self.expression(arg) for arg in node.args]
            if node.func.id == "sum" and (len(args) != 1 or not isinstance(args[0], list)
                    or not all(type(item) in (int, float) for item in args[0])):
                raise ValueError("sum requires a list of numbers")
            return self.bounded(FUNCTIONS[node.func.id](*args))
        raise ValueError(f"Unsupported Python expression: {type(node).__name__}")

    def statements(self, nodes):
        for node in nodes:
            self.step(node)
            if isinstance(node, ast.If):
                self.statements(node.body if self.expression(node.test) else node.orelse)
                continue
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                value = self.bounded(self.expression(node.value))
                if isinstance(target, ast.Name) and target.id != "response":
                    self.values[target.id] = value
                    continue
                if (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)
                        and target.value.id == "result" and isinstance(self.values["result"], dict)):
                    key = self.expression(target.slice)
                    if not isinstance(key, str):
                        raise ValueError("Result keys must be strings")
                    self.values["result"][key] = value
                    self.bounded(self.values["result"])
                    continue
            raise ValueError(f"Unsupported Python statement: {type(node).__name__}")


def calculate(payload):
    calculation = Calculation(payload["answers"])
    try:
        # Substitute only identifier syntax. Answers themselves are bound as data.
        code = REFERENCES.sub(lambda match: "response[" + repr(match[1]) + "]", payload["code"])
        tree = ast.parse(code)
        if sum(1 for _ in ast.walk(tree)) > 500:
            raise ValueError("Calculation exceeds the syntax size limit")
        calculation.statements(tree.body)
        result = calculation.values["result"]
        if not isinstance(result, dict) or not all(isinstance(key, str) for key in result):
            raise ValueError("result must be a dictionary with string keys")
        return {"result": calculation.bounded(result)}
    except (SyntaxError, ValueError, TypeError, KeyError, IndexError, ArithmeticError, RecursionError) as exc:
        message = f"Unknown or unanswered reference: {exc.args[0]}" if isinstance(exc, KeyError) else str(exc)
        return {"error": type(exc).__name__, "message": message[:500],
                "line": getattr(exc, "lineno", None) or calculation.line}


if __name__ == "__main__":
    print(json.dumps(calculate(json.load(sys.stdin)), ensure_ascii=True))
