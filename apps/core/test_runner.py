from django.apps import apps
from django.test.runner import DiscoverRunner


class InstalledAppsOnlyDiscoverRunner(DiscoverRunner):
    def build_suite(self, test_labels=None, extra_tests=None, **kwargs):
        if not test_labels:
            test_labels = [
                app_config.name
                for app_config in apps.get_app_configs()
                if app_config.name.startswith('apps.')
            ]
        return super().build_suite(test_labels=test_labels, extra_tests=extra_tests, **kwargs)
