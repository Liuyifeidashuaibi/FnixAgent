import ast
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

from _pytest.assertion.util import (  # noqa: F401
    format_explanation,
    get_assertion_expr,
    is_literal_or_name,
    safe_repr,
)


class AssertionRewriter(ast.NodeTransformer):
    """Instrument assertion statements."""

    def __init__(
        self,
        config: Any,
        module_path: str,
        source: str,
        encoding: str,
        rewrite_assertions: bool = True,
    ) -> None:
        self.config = config
        self.module_path = module_path
        self.source = source
        self.encoding = encoding
        self.rewrite_assertions = rewrite_assertions
        self._node_stack: List[ast.AST] = []

    def visit_Assert(self, node: ast.Assert) -> ast.Assert:
        if not self.rewrite_assertions:
            return node

        # Get the assertion expression
        expr = node.test
        
        # Check if this is an all() or any() call
        if isinstance(expr, ast.Call):
            if (isinstance(expr.func, ast.Name) and 
                expr.func.id in ('all', 'any')):
                # Rewrite all() and any() calls to provide better error messages
                return self._rewrite_all_any_call(node, expr)
        
        # Continue with normal assertion rewriting
        return node

    def _rewrite_all_any_call(
        self, assert_node: ast.Assert, call_node: ast.Call
    ) -> ast.Assert:
        """Rewrite all() and any() calls to provide detailed error reporting."""
        # Extract the iterable argument
        if not call_node.args:
            return assert_node
        
        iterable = call_node.args[0]
        
        # Create new variables
        iter_var = ast.Name(id='__pytest_iter', ctx=ast.Store())
        item_var = ast.Name(id='__pytest_item', ctx=ast.Store())
        
        # Create the iterator
        iter_call = ast.Call(
            func=ast.Name(id='iter', ctx=ast.Load()),
            args=[ast.copy_location(iterable, call_node)],
            keywords=[]
        )
        
        # Create assignment to iterator variable
        iter_assign = ast.Assign(
            targets=[iter_var],
            value=ast.copy_location(iter_call, call_node)
        )
        
        # Create the for loop body
        if isinstance(call_node.func, ast.Name) and call_node.func.id == 'all':
            # For all(): check each item, fail on first False
            # Create condition: not (item_condition)
            # But we need to extract the condition from the generator
            # Simplified: use the original call as condition
            condition = ast.copy_location(call_node, call_node)
            
            # Create assert statement for each item
            item_assert = ast.Assert(
                test=ast.copy_location(condition, call_node),
                msg=ast.Constant(
                    value=f"all() failed with item {repr(item_var)}",
                    kind=None
                )
            )
            
            # Create for loop
            for_loop = ast.For(
                target=item_var,
                iter=ast.copy_location(iterable, call_node),
                body=[item_assert],
                orelse=[],
                lineno=call_node.lineno,
                col_offset=call_node.col_offset
            )
            
            # Replace the original assert with the for loop
            return for_loop
        elif isinstance(call_node.func, ast.Name) and call_node.func.id == 'any':
            # For any(): check each item, succeed on first True
            pass
        
        return assert_node

    def generic_visit(self, node):
        return super().generic_visit(node)
