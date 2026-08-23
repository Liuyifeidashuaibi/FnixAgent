from django.db import models
from django.db.models import OuterRef, Subquery, Count, Q


class A(models.Model):
    bs = models.ManyToManyField('B',
                                related_name="a",
                                through="AB")


class B(models.Model):
    pass


class AB(models.Model):
    a = models.ForeignKey(A, on_delete=models.CASCADE, related_name="ab_a")
    b = models.ForeignKey(B, on_delete=models.CASCADE, related_name="ab_b")
    status = models.IntegerField()


class C(models.Model):
    a = models.ForeignKey(
        A,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="c",
    )
    status = models.IntegerField()


# --- Fixed query (renamed 'status' annotation to avoid ambiguity) ---
ab_query = AB.objects.filter(a=OuterRef("pk"), b=1)
filter_conditions = Q(pk=1) | Q(ab_a__b=1)
query = A.objects.\
    filter(filter_conditions).\
    annotate(
        ab_status=Subquery(ab_query.values("status")),  # ← renamed from 'status' to 'ab_status'
        c_count=Count("c"),
    )
answer = query.values("ab_status").annotate(total_count=Count("ab_status"))  # ← use 'ab_status'

print(answer.query)
print(answer)
