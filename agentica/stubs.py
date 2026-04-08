"""
Vibe coded stub printer for showing python values to LLMs.
"""

import inspect
import typing as _t
from collections.abc import Collection, Mapping

_SENTINEL = object()
_DEFAULT_PREVIEW_LEN = 40


def _safe_repr(obj: object, max_len: int = _DEFAULT_PREVIEW_LEN) -> str:
    """repr(obj) but truncated and made single-line."""
    try:
        r = repr(obj)
    except Exception as exc:
        r = f"<unrepresentable {type(obj).__name__}: {exc}>"
    r = r.replace("\n", " ").strip()
    return (r[: max_len - 1] + "…") if len(r) > max_len else r


def _format_docstring(obj: object, indent: str = "") -> str:
    """Extract and format docstring with proper indentation."""
    try:
        docstring = inspect.getdoc(obj)
        if not docstring:
            return ""

        # Split into lines and add proper indentation
        lines = docstring.split("\n")
        # First line goes on the same line as the triple quotes
        if len(lines) == 1:
            return f'{indent}"""{lines[0]}"""'

        # Multi-line docstring
        formatted_lines = [f'{indent}"""{lines[0]}']
        for line in lines[1:]:
            # Add indent to each subsequent line
            formatted_lines.append(f"{indent}{line}" if line.strip() else f"{indent}")
        formatted_lines.append(f'{indent}"""')
        return "\n".join(formatted_lines)
    except Exception:
        return ""


_BUILTIN_TYPES = frozenset(
    {"int", "str", "float", "bool", "dict", "list", "tuple", "set", "bytes", "NoneType"}
)


def clean_type_name(type_obj: object, context: dict[str, _t.Any]) -> str:
    """Get a clean, readable type name from a type object and add it to context."""
    # Handle generic types like List[str], Dict[str, int]
    origin = getattr(type_obj, "__origin__", None)
    if origin is not None:
        # For parameterized generics, we want the base type (List, not List[str])
        if hasattr(type_obj, "_name") and getattr(type_obj, "_name"):
            name = getattr(type_obj, "_name")
            # Try to get the actual typing class
            try:
                import typing as typing_mod

                actual_type = getattr(typing_mod, name, None)
                if actual_type:
                    context[name] = actual_type
            except Exception:
                context[name] = type_obj

        # Also process any type arguments
        args = getattr(type_obj, "__args__", ())
        for arg in args:
            clean_type_name(arg, context)

        # Return the clean representation
        return repr(type_obj).replace("typing.", "")

    # Handle built-in types
    if hasattr(type_obj, "__name__"):
        name = getattr(type_obj, "__name__", "")
        if name in _BUILTIN_TYPES:
            return name
        else:
            # Add non-builtin types to context
            context[name] = type_obj
            return name

    # Handle typing constructs like Optional (when not parameterized)
    if hasattr(type_obj, "_name"):
        name = getattr(type_obj, "_name", None)
        if name and name not in _BUILTIN_TYPES:
            try:
                import typing as typing_mod

                actual_type = getattr(typing_mod, name, None)
                if actual_type:
                    context[name] = actual_type
                else:
                    context[name] = type_obj
            except Exception:
                context[name] = type_obj
            return name

    # Fallback: use repr and clean it up
    type_repr = repr(type_obj)
    type_repr = type_repr.replace("typing.", "")
    type_repr = type_repr.replace("<class '", "").replace("'>", "")

    return "None" if type_repr == "NoneType" else type_repr


def _format_collection_sample(items: list, max_items: int = 3) -> str:
    """Format a sample of collection items with ellipsis if truncated."""
    sample_items = [_safe_repr(x) for x in items[:max_items]]
    sample = ", ".join(sample_items)
    return f"{sample}, ..." if len(items) > max_items else sample


def _format_dict_stub(name: str, val: Mapping) -> str:
    """Format a dictionary stub with proper syntax."""
    if len(val) == 0:
        return f"{name}: {type(val).__name__} = {{}}"

    items = list(val.items())
    samples = [f"{_safe_repr(k)}: {_safe_repr(v)}" for k, v in items[:3]]
    sample_str = ", ".join(samples)
    if len(val) > 3:
        sample_str += ", ..."
    return f"{name}: {type(val).__name__} = {{{sample_str}}}"


def _format_sequence_stub(name: str, val: Collection) -> str:
    """Format list/tuple stub with proper brackets."""
    is_tuple = isinstance(val, tuple)
    if len(val) == 0:
        brackets = "()" if is_tuple else "[]"
        return f"{name}: {type(val).__name__} = {brackets}"

    sample = _format_collection_sample(list(val))
    brackets = f"({sample})" if is_tuple else f"[{sample}]"
    return f"{name}: {type(val).__name__} = {brackets}"


def _format_set_stub(name: str, val: set) -> str:
    """Format set stub with proper syntax."""
    if len(val) == 0:
        return f"{name}: {type(val).__name__} = set()"

    sample = _format_collection_sample(list(val))
    return f"{name}: {type(val).__name__} = {{{sample}}}"


def _format_function_stub(
    name: str, func: object, context: dict[str, _t.Any], indent: str = ""
) -> str:
    """Format a function or method stub with type annotations and docstring."""
    try:
        ann = _t.get_type_hints(func, include_extras=True)
        sig = inspect.signature(func)  # type: ignore[arg-type]

        # Check if the function is async
        is_async = inspect.iscoroutinefunction(func)
        async_prefix = "async " if is_async else ""

        # Re-insert annotations that were stripped off the signature by typing
        params = []
        for p in sig.parameters.values():
            ann_str = ""
            if p.name in ann:
                type_obj = ann[p.name]
                type_repr = clean_type_name(type_obj, context)
                ann_str = f": {type_repr}"

            default = ""
            if p.default is not inspect._empty:
                default = f" = {_safe_repr(p.default)}"

            params.append(f"{p.name}{ann_str}{default}")

        ret = ""
        if "return" in ann:
            ret_obj = ann["return"]
            ret_repr = clean_type_name(ret_obj, context)
            ret = f" -> {ret_repr}"

        param_s = ", ".join(params)
        docstring = _format_docstring(func, indent + "    ")
        signature = f"{indent}{async_prefix}def {name}({param_s}){ret}:"

        return f"{signature}\n{docstring}" if docstring else f"{signature} ..."
    except Exception:
        return f"{indent}def {name}(): ..."


def _stub_for_value(name: str, val: object, context: dict[str, _t.Any]) -> str:
    """Dispatch to the right stub builder based on *val*'s type."""
    # Add the value itself to context if it's a class, function, or type
    if isinstance(val, type) or inspect.isfunction(val) or inspect.ismethod(val):
        context[name] = val

    if inspect.isfunction(val) or inspect.ismethod(val):
        return _format_function_stub(name, val, context)
    elif isinstance(val, type):
        bases = [b.__name__ for b in val.__bases__ if b is not object]
        base_s = f"({', '.join(bases)})" if bases else ""

        # Get the class docstring
        class_docstring = _format_docstring(val, "    ")

        # Get methods and attributes from the class
        members = []
        if class_docstring:
            members.append(class_docstring)

        for attr_name, attr_val in sorted(inspect.getmembers(val)):
            if attr_name.startswith("_") and attr_name != "__init__":
                continue  # Skip private/special methods except __init__

            try:
                if inspect.isfunction(attr_val) or inspect.ismethod(attr_val):
                    # Use the shared function stub formatter with indentation
                    method_stub = _format_function_stub(
                        attr_name, attr_val, context, "    "
                    )
                    members.append(method_stub)
                elif not callable(attr_val):
                    # Class attribute
                    type_name = type(attr_val).__name__
                    repr_val = _safe_repr(attr_val)
                    members.append(f"    {attr_name}: {type_name} = {repr_val}")
            except Exception:
                # Fallback for problematic attributes
                type_name = getattr(type(attr_val), "__name__", "object")
                members.append(f"    {attr_name}: {type_name}")

        if members:
            member_str = "\n" + "\n".join(members)
        else:
            member_str = " ..."

        return f"class {name}{base_s}:{member_str}"
    elif isinstance(val, (int, float, str, bool, bytes, complex)):
        return f"{name}: {type(val).__name__} = {_safe_repr(val)}"
    elif isinstance(val, Mapping) and not isinstance(val, (str, bytes)):
        return _format_dict_stub(name, val)
    elif isinstance(val, Collection) and not isinstance(val, (str, bytes)):
        if isinstance(val, (list, tuple)):
            return _format_sequence_stub(name, val)
        elif isinstance(val, set):
            return _format_set_stub(name, val)
        else:
            # Other collections - fallback to generic format
            sample = _format_collection_sample(list(val))
            extra = f"[{sample}]" if sample else ""
            return f"{name}: {type(val).__name__} (len={len(val)}) {extra}"
    else:
        # For object instances, add the class to context and show a clean representation
        val_type = type(val)
        type_name = val_type.__name__

        # Special case for modules - keep the descriptive format
        if isinstance(val, type(_t)):  # Check if it's a module
            return f"{name}: {type_name} = {_safe_repr(val)}"

        # Add the class to context so LLM can access it
        if type_name not in _BUILTIN_TYPES:
            context[type_name] = val_type

        # Show a clean representation without misleading module paths
        return f"{name}: {type_name} = <{type_name} object>"


def emit_stubs(
    ns: dict[str, _t.Any] | None = None,
    *,
    max_lines: int | None = None,
    exclude_private: bool = True,
) -> tuple[str, dict[str, _t.Any]]:
    """
    Return stubs and required context for every binding in *ns* (defaults to caller's globals()).

    Parameters
    ----------
    ns : dict | None
        Namespace to inspect.  If None, inspect the caller's frame.
    max_lines : int | None
        Truncate the output to at most *max_lines* lines (helps huge notebooks).
    exclude_private : bool
        Skip names that start with an underscore.

    Returns
    -------
    tuple[str, dict[str, Any]]
        A tuple of (stub_string, required_context) where required_context
        contains all types and objects referenced in the stubs.
    """
    if ns is None:
        frame = inspect.currentframe()
        if frame and frame.f_back:
            ns = frame.f_back.f_globals
        else:
            ns = {}

    required_context: dict[str, _t.Any] = {}
    lines: list[str] = []
    for name, val in sorted(ns.items()):
        if exclude_private and name.startswith("_"):
            continue
        lines.append(_stub_for_value(name, val, required_context))
        if max_lines is not None and len(lines) >= max_lines:
            break

    return "\n\n".join(lines), required_context


# --- Convenience one-liner ----------------------------------------------------
def print_stubs(max_lines: int | None = None, *, exclude_private: bool = True):
    """Print stubs for the caller's globals()."""
    stubs, _ = emit_stubs(max_lines=max_lines, exclude_private=exclude_private)
    print(stubs)
