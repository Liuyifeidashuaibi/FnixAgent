diff --git a/src/_pytest/runner.py b/src/_pytest/runner.py
index 1234567..89abcde 100644
--- a/src/_pytest/runner.py
+++ b/src/_pytest/runner.py
@@ -123,7 +123,10 @@ class ExceptionInfo:
     def __str__(self):
         """Return a formatted string of the exception."""
         if self.typename is None:
-            return "<no exception info>"
+            return "<no exception info>"
+        if self.value is not None:
+            return str(self.value)
+        return f"{self.typename}: {self.exconly()}"
         return f"{self.typename}: {self.exconly()}"
 
     def exconly(self, tryshort=False):