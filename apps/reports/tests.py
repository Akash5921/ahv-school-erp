from django.test import TestCase
from django.urls import reverse

from apps.dashboard.tests import DashboardBaseTestCase


class ReportViewTests(DashboardBaseTestCase):
    def test_fee_collection_report_exports_pdf_and_excel(self):
        self.client.login(username='phase11_accountant', password='pass12345')

        html_response = self.client.get(reverse('report_detail', args=['fee-collection']))
        self.assertEqual(html_response.status_code, 200)
        self.assertContains(html_response, 'Fee Collection Report')

        pdf_response = self.client.get(reverse('report_detail', args=['fee-collection']), {'export': 'pdf'})
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response['Content-Type'], 'application/pdf')

        xlsx_response = self.client.get(reverse('report_detail', args=['fee-collection']), {'export': 'xlsx'})
        self.assertEqual(xlsx_response.status_code, 200)
        self.assertIn('spreadsheetml.sheet', xlsx_response['Content-Type'])

    def test_teacher_cannot_access_payroll_report(self):
        self.client.login(username='phase11_teacher', password='pass12345')
        response = self.client.get(reverse('report_detail', args=['monthly-payroll']))
        self.assertEqual(response.status_code, 403)

    def test_class_strength_report_shows_filtered_student_rows(self):
        self.client.login(username='phase11_teacher', password='pass12345')
        response = self.client.get(reverse('report_detail', args=['class-strength']), {
            'session': self.session.id,
            'school_class': self.school_class.id,
            'section': self.section.id,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Class Strength Report')
        self.assertContains(response, '8th')
        self.assertContains(response, '1')

    def test_locked_session_is_view_only_for_exports(self):
        self.session.attendance_locked = True
        self.session.save(update_fields=['attendance_locked'])

        self.client.login(username='phase11_accountant', password='pass12345')
        html_response = self.client.get(reverse('report_detail', args=['fee-collection']), {
            'session': self.session.id,
        })
        self.assertEqual(html_response.status_code, 200)
        self.assertContains(html_response, 'view-only access is enabled')

        export_response = self.client.get(reverse('report_detail', args=['fee-collection']), {
            'session': self.session.id,
            'export': 'pdf',
        })
        self.assertEqual(export_response.status_code, 403)


class ReportIndexTests(DashboardBaseTestCase):
    def test_teacher_report_index_hides_payroll_reports(self):
        self.client.login(username='phase11_teacher', password='pass12345')
        response = self.client.get(reverse('report_index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Advanced Reports & Analytics')
        self.assertContains(response, 'Class Strength Report')
        self.assertNotContains(response, 'Monthly Payroll')

    def test_parent_cannot_access_report_index(self):
        self.client.login(username='phase11_parent', password='pass12345')
        response = self.client.get(reverse('report_index'))
        self.assertEqual(response.status_code, 403)
