from django.core.exceptions import NotImplementedError

class CombinedQuerySet:
    def distinct(self, *field_names):
        if field_names:
            raise NotImplementedError(
                "DISTINCT ON fields is not supported for combined queries."
            )
        return super().distinct(*field_names)
