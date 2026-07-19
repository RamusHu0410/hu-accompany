from django.db import models


class Work(models.Model):
    title = models.CharField(max_length=500)
    composer = models.CharField(max_length=500, blank=True)
    imslp_url = models.URLField(max_length=1000, unique=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.composer})"


class Version(models.Model):
    work = models.ForeignKey(Work, related_name="versions", on_delete=models.CASCADE)
    name = models.CharField(max_length=500)
    instrumentation = models.CharField(max_length=500, blank=True)
    type = models.CharField(max_length=50)
    movement = models.CharField(max_length=500, blank=True, null=True)
    arranger = models.CharField(max_length=500, blank=True, null=True)
    editor = models.CharField(max_length=500, blank=True, null=True)
    imslp_url = models.URLField(max_length=1000)
    file_name = models.CharField(max_length=500, blank=True, null=True)

    def __str__(self):
        return f"{self.name} [{self.work_id}]"
