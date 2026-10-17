"""Offline regression tests: python -m unittest discover -s tests -p test_update_data.py -v."""
import contextlib
import copy
import io
import os
import unittest
from unittest.mock import patch

from backend.db import MemoryStore
from scripts import pipeline, update_data


class UpdateDataTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.store.set('regions', '4812310100', {'name': '상남동'})
        for collection in ('monthly_data', 'region_latest'):
            self.store.set(collection, 'existing', {'metrics': {'population': 154}})
        self.before = copy.deepcopy(self.store._data)
        for patcher in (
            patch.dict(os.environ, {'DATA_GO_KR_SERVICE_KEY': 'test-secret-key'}, clear=True),
            patch.object(update_data, 'get_store', return_value=self.store),
            patch.object(pipeline, 'get_store', return_value=self.store),
            patch.object(update_data, 'current_month', return_value='2026-01'),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_main(self, scope):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = update_data.main(scope)
        return code, output.getvalue()

    def test_default_endpoints_need_no_url_overrides(self):
        for source in ('apt_sale', 'apt_rent', 'other_real_estate',
                       'apartment_basic', 'building_register', 'commerce'):
            self.assertEqual(update_data._missing_config(source), [])

    def test_missing_key_and_whitespace_config(self):
        os.environ['DATA_GO_KR_SERVICE_KEY'] = ' '
        self.assertEqual(update_data._missing_config('apt_sale'), ['DATA_GO_KR_SERVICE_KEY'])
        os.environ['POPULATION_API_URL'] = ' '
        self.assertIn('POPULATION_API_URL', update_data._missing_config('population'))

    def test_population_sources_require_url_and_query(self):
        for source in ('population', 'age_population', 'single_household'):
            prefix = source.upper()
            self.assertTrue(update_data._missing_config(source))
            os.environ[prefix + '_API_URL'] = 'https://example.invalid'
            self.assertEqual(update_data._missing_config(source), [prefix + '_QUERY_JSON'])
            os.environ[prefix + '_QUERY_JSON'] = '{"month":"{yyyymm}"}'
            self.assertEqual(update_data._missing_config(source), [])

    def test_optional_endpoint_alternatives(self):
        for source, prefixes in (
            ('onbid', ('ONBID_PROPERTY', 'ONBID_RESULT')),
            ('household_birth_death', ('HOUSEHOLD_SIZE', 'BIRTH_DEATH', 'BIRTH', 'DEATH')),
        ):
            for prefix in prefixes:
                with patch.dict(os.environ, {
                    prefix + '_API_URL': 'https://example.invalid',
                    prefix + '_QUERY_JSON': '{"month":"{yyyymm}"}',
                }):
                    self.assertEqual(update_data._missing_config(source), [])
            self.assertTrue(update_data._missing_config(source))

    def test_every_enabled_endpoint_needs_query(self):
        os.environ.update(ONBID_PROPERTY_API_URL='url', ONBID_PROPERTY_QUERY_JSON='{}',
                          ONBID_RESULT_API_URL='url')
        self.assertEqual(update_data._missing_config('onbid'), ['ONBID_RESULT_QUERY_JSON'])

    def test_skip_records_reason_without_changing_data(self):
        self.store.set('source_status', 'onbid_2026-01', {'error': 'stale error'})
        row = update_data._skip_row('onbid', '2026-01')
        saved = self.store.get('source_status', 'onbid_2026-01')
        self.assertEqual(saved['status'], 'skipped')
        self.assertEqual(saved['reason'], 'missing_config')
        self.assertTrue(row['finished_at'])
        self.assertNotIn('error', saved)
        self.assertNotIn('test-secret-key', str(saved))
        for collection in ('monthly_data', 'region_latest'):
            self.assertEqual(self.store._data[collection], self.before[collection])

    def test_daily_recalculates_three_months_across_year_boundary(self):
        with patch.object(update_data, 'run_source', side_effect=lambda s, m:
                          {'source': s, 'month': m, 'status': 'ok'}) as run:
            code, output = self.run_main('daily')
        self.assertEqual(code, 0)
        self.assertEqual(run.call_count, 9)
        self.assertEqual([c.args for c in run.call_args_list],
                         [(s, m) for m in ('2025-11', '2025-12', '2026-01')
                          for s in ('apt_sale', 'apt_rent', 'other_real_estate')])
        self.assertIn('ok=9, error=0, skipped/planned=3', output)

    def test_monthly_and_all_preserve_planned_and_skip_paths(self):
        for scope, expected_calls in (('monthly', 3), ('all', 12)):
            with self.subTest(scope=scope), patch.object(
                update_data, 'run_source', return_value={'status': 'ok'}
            ) as run:
                self.assertEqual(self.run_main(scope)[0], 0)
                self.assertEqual(run.call_count, expected_calls)
                self.assertEqual(self.store.get('source_status', 'kosis_2025-12')['status'],
                                 'planned_adapter_pending')

    def test_month_override_and_recalc_minimum(self):
        os.environ.update(MONTHLY_TARGET_MONTH='2025-09', RECENT_REAL_ESTATE_RECALC_MONTHS='0')
        with patch.object(update_data, 'run_source', return_value={'status': 'ok'}) as run:
            self.assertEqual(self.run_main('all')[0], 0)
            self.assertEqual(run.call_count, 6)
            self.assertEqual(run.call_args_list[-1].args[1], '2025-09')

    def test_empty_regions_exit_before_collecting(self):
        self.store.delete('regions', '4812310100')
        with patch.object(update_data, 'run_source') as run:
            self.assertEqual(self.run_main('daily')[0], 2)
            run.assert_not_called()

    def test_invalid_query_uses_existing_error_logging(self):
        os.environ.update(POPULATION_API_URL='https://example.invalid',
                          POPULATION_QUERY_JSON='not-json')
        self.assertEqual(update_data._missing_config('population'), [])
        with patch.object(update_data, 'MONTHLY', ['population']), patch.object(update_data, 'PLANNED', []):
            self.assertEqual(self.run_main('monthly')[0], 1)
        row = self.store.get('source_status', 'population_2025-12')
        self.assertEqual(row['status'], 'error')
        self.assertIn('JSON', row['error'])

    def test_successful_refresh_upserts_without_erasing_other_metrics(self):
        rid = '4812310100'
        self.store.set('monthly_data', rid + '_2026-01',
                       {'region_id': rid, 'month': '2026-01',
                        'metrics': {'population': 154, 'sale_count': 1}})
        os.environ.update(RECENT_REAL_ESTATE_RECALC_MONTHS='1', DEFER_INDEX_RECOMPUTE='true')
        with patch.object(update_data, 'DAILY', ['apt_sale']), patch.object(
            pipeline, 'COLLECTORS',
            {'apt_sale': (lambda month: {rid: {'sale_count': 3}}, 'sale_count', True)}
        ):
            self.assertEqual(self.run_main('daily')[0], 0)
        row = self.store.get('monthly_data', rid + '_2026-01')
        self.assertEqual(row['metrics'], {'population': 154, 'sale_count': 3})
        self.assertEqual(row['freshness']['sources']['apt_sale']['sample_size'], 3)
        self.assertEqual(self.store.get('region_latest', rid)['metrics'], row['metrics'])
        self.assertEqual(self.store.get('source_status', 'apt_sale_2026-01')['regions_updated'], 1)

    def test_collector_error_is_redacted_and_later_sources_continue(self):
        def fail(month):
            raise RuntimeError('serviceKey=test-secret-key')
        collectors = {
            'apt_sale': (fail, None, True),
            'apt_rent': (lambda month: {'4812310100': {'rent_count': 2}}, 'rent_count', True),
            'other_real_estate': (lambda month: {}, None, True),
        }
        with patch.object(pipeline, 'COLLECTORS', collectors), patch.object(
            pipeline, 'apply_patches', return_value=1
        ) as apply:
            code, output = self.run_main('daily')
        self.assertEqual(code, 1)
        self.assertEqual(apply.call_count, 6)
        self.assertIn('ok=6, error=3, skipped/planned=3', output)
        for month in ('2025-11', '2025-12', '2026-01'):
            error = self.store.get('source_status', 'apt_sale_' + month)
            self.assertEqual(error['status'], 'error')
            self.assertIn('[REDACTED]', error['error'])
            self.assertNotIn('test-secret-key', error['error'])
            self.assertEqual(self.store.get('source_status', 'apt_rent_' + month)['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
