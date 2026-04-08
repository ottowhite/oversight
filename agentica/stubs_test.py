#!/usr/bin/env python3
"""Unit tests for stub generation functionality."""

import sys
import unittest
from typing import List, Optional

from stubs import _stub_for_value, emit_stubs


class TestClass:
    """A test class with various methods and attributes."""

    class_var: str = "test_value"
    count = 42

    def __init__(self, name: str, age: int = 25):
        self.name = name
        self.age = age

    def greet(self, greeting: str = "Hello") -> str:
        """Return a greeting message."""
        return f"{greeting}, {self.name}!"

    def calculate(self, x: int, y: int) -> int:
        """Add two numbers."""
        return x + y

    def get_info(self) -> dict:
        """Get info about this instance."""
        return {"name": self.name, "age": self.age}

    def process_items(self, items: List[str], filter_empty: bool = True) -> List[str]:
        """Process a list of items."""
        if filter_empty:
            return [item for item in items if item.strip()]
        return items


class EmptyClass:
    """Class with no public methods or attributes."""

    pass


class ClassWithPrivateMethods:
    """Class with private methods that should be hidden."""

    def public_method(self) -> None:
        pass

    def _private_method(self) -> None:
        pass

    def __special_method__(self) -> None:
        pass


def standalone_function(a: int, b: str = "default", c: Optional[float] = None) -> bool:
    """A standalone function for testing."""
    return True


def simple_function():
    """Function without type hints."""
    pass


class TestStubGeneration(unittest.TestCase):
    """Test cases for stub generation functionality."""

    def test_standalone_function_with_types(self):
        """Test stub generation for standalone function with type annotations."""
        context = {}
        result = _stub_for_value("standalone_function", standalone_function, context)
        expected = '''def standalone_function(a: int, b: str = \'default\', c: Optional[float] = None) -> bool:
    """A standalone function for testing."""'''
        self.assertEqual(result, expected)

    def test_simple_function_without_types(self):
        """Test stub generation for function without type annotations."""
        context = {}
        result = _stub_for_value("simple_function", simple_function, context)
        expected = '''def simple_function():
    """Function without type hints."""'''
        self.assertEqual(result, expected)

    def test_class_with_methods(self):
        """Test that classes show their methods and attributes."""
        context = {}
        result = _stub_for_value("TestClass", TestClass, context)
        # Just check that key components are present rather than exact match
        self.assertIn("class TestClass:", result)
        self.assertIn("def __init__(self, name: str, age: int = 25):", result)
        self.assertIn("def calculate(self, x: int, y: int) -> int:", result)
        self.assertIn("class_var: str = 'test_value'", result)
        self.assertIn("count: int = 42", result)
        self.assertIn("def get_info(self) -> dict:", result)
        self.assertIn("def greet(self, greeting: str = 'Hello') -> str:", result)
        self.assertIn(
            "def process_items(self, items: List[str], filter_empty: bool = True) -> List[str]:",
            result,
        )

    def test_class_variable(self):
        """Test stub generation for class variables."""
        context = {}
        result = _stub_for_value("class_var", TestClass.class_var, context)
        expected = "class_var: str = 'test_value'"
        self.assertEqual(result, expected)

    def test_instance_method(self):
        """Test stub generation for instance methods."""
        instance = TestClass("test")
        context = {}
        result = _stub_for_value("greet", instance.greet, context)
        expected = '''def greet(greeting: str = \'Hello\') -> str:
    """Return a greeting message."""'''
        self.assertEqual(result, expected)

    def test_empty_class(self):
        """Test stub generation for empty classes."""
        context = {}
        result = _stub_for_value("EmptyClass", EmptyClass, context)
        expected = '''class EmptyClass:
    """Class with no public methods or attributes."""'''
        self.assertEqual(result, expected)

    def test_class_with_private_methods(self):
        """Test that private methods are hidden but public methods are shown."""
        context = {}
        result = _stub_for_value(
            "ClassWithPrivateMethods", ClassWithPrivateMethods, context
        )
        expected = '''class ClassWithPrivateMethods:
    """Class with private methods that should be hidden."""
    def public_method(self) -> NoneType: ...'''
        self.assertEqual(result, expected)

    def test_module_object(self):
        """Test stub generation for module objects."""
        context = {}
        result = _stub_for_value("sys", sys, context)
        expected = "sys: module = <module 'sys' (built-in)>"
        self.assertEqual(result, expected)

    def test_full_namespace_generation(self):
        """Test generating stubs for a complete namespace."""
        test_namespace = {
            "TestClass": TestClass,
            "standalone_function": standalone_function,
            "simple_function": simple_function,
            "test_int": 42,
            "test_str": "hello",
            "test_list": [1, 2, 3],
        }

        result, context = emit_stubs(test_namespace)

        # Check that all expected items are present
        self.assertIn("class TestClass:", result)
        self.assertIn("def __init__(self, name: str, age: int = 25):", result)
        self.assertIn(
            "def standalone_function(a: int, b: str = 'default', c: Optional[float] = None) -> bool:",
            result,
        )
        self.assertIn("def simple_function():", result)
        self.assertIn("test_int: int = 42", result)
        self.assertIn("test_str: str = 'hello'", result)
        self.assertIn("test_list: list = [1, 2, 3]", result)

    def test_class_methods_include_init(self):
        """Test that __init__ methods are included in class stubs."""
        context = {}
        result = _stub_for_value("TestClass", TestClass, context)
        self.assertIn("def __init__(self, name: str, age: int = 25):", result)

    def test_type_annotations_are_clean(self):
        """Test that type annotations display cleanly."""
        context = {}
        result = _stub_for_value("standalone_function", standalone_function, context)
        # Should show clean types, not <class 'int'>
        self.assertIn("a: int", result)
        self.assertIn("b: str", result)
        self.assertIn("-> bool", result)
        # Should preserve generic types
        self.assertIn("Optional[float]", result)

    def test_generic_types_preserved(self):
        """Test that generic types like List[str] are preserved."""
        context = {}
        result = _stub_for_value("TestClass", TestClass, context)
        self.assertIn("List[str]", result)

    def test_class_attributes_included(self):
        """Test that class attributes are included in stubs."""
        context = {}
        result = _stub_for_value("TestClass", TestClass, context)
        self.assertIn("class_var: str = 'test_value'", result)
        self.assertIn("count: int = 42", result)

    def test_emit_stubs_returns_context(self):
        """Test that emit_stubs returns both stubs and required context."""
        test_namespace = {
            "TestClass": TestClass,
            "standalone_function": standalone_function,
            "test_int": 42,
            "test_str": "hello",
        }

        # New behavior - should return tuple
        result = emit_stubs(test_namespace)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

        stubs_str, context_dict = result
        self.assertIsInstance(stubs_str, str)
        self.assertIsInstance(context_dict, dict)

        # Check that the stubs string contains expected content
        self.assertIn("class TestClass:", stubs_str)
        self.assertIn("def standalone_function", stubs_str)
        self.assertIn("test_int: int = 42", stubs_str)

        # Check that context contains required types/classes
        # TestClass should be in context since it's referenced in the stub
        self.assertIn("TestClass", context_dict)
        self.assertEqual(context_dict["TestClass"], TestClass)

        # standalone_function should be in context
        self.assertIn("standalone_function", context_dict)
        self.assertEqual(context_dict["standalone_function"], standalone_function)

        # Types like List should be in context when used in annotations
        if "List" in stubs_str:
            self.assertIn("List", context_dict)


if __name__ == "__main__":
    unittest.main()
