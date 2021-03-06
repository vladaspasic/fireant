from unittest import TestCase
from unittest.mock import (
    Mock,
    call,
    patch,
)

import fireant as f
from fireant.tests.slicer.mocks import (
    ElectionOverElection,
    slicer,
)
from fireant.utils import format_metric_key


@patch('fireant.slicer.queries.builder.scrub_totals_from_share_results', side_effect=lambda *args, **kwargs: args[0])
@patch('fireant.slicer.queries.builder.paginate', side_effect=lambda *args, **kwargs: args[0])
@patch('fireant.slicer.queries.builder.fetch_data')
class QueryBuilderOperationsTests(TestCase):
    def test_operations_evaluated(self, mock_fetch_data: Mock, *mocks):
        mock_operation = Mock(name='mock_operation ', spec=f.Operation)
        mock_operation.key, mock_operation.definition = 'mock_operation', slicer.table.abc
        mock_operation.metrics = []

        mock_widget = f.Widget(mock_operation)
        mock_widget.transform = Mock()

        mock_df = {}
        mock_fetch_data.return_value = mock_df

        # Need to keep widget the last call in the chain otherwise the object gets cloned and the assertion won't work
        slicer.data \
            .dimension(slicer.dimensions.timestamp) \
            .widget(mock_widget) \
            .fetch()

        mock_operation.apply.assert_called_once_with(mock_df, None)

    def test_operations_evaluated_for_each_reference(self, mock_fetch_data: Mock, *mocks):
        eoe = ElectionOverElection(slicer.dimensions.timestamp)

        mock_operation = Mock(name='mock_operation ', spec=f.Operation)
        mock_operation.key, mock_operation.definition = 'mock_operation', slicer.table.abc
        mock_operation.metrics = []

        mock_widget = f.Widget(mock_operation)
        mock_widget.transform = Mock()

        mock_df = {}
        mock_fetch_data.return_value = mock_df

        # Need to keep widget the last call in the chain otherwise the object gets cloned and the assertion won't work
        slicer.data \
            .dimension(slicer.dimensions.timestamp) \
            .reference(eoe) \
            .widget(mock_widget) \
            .fetch()

        mock_operation.apply.assert_has_calls([
            call(mock_df, None),
            call(mock_df, eoe),
        ])

    def test_operations_results_stored_in_data_frame(self, mock_fetch_data: Mock, *mocks):
        mock_operation = Mock(name='mock_operation ', spec=f.Operation)
        mock_operation.key, mock_operation.definition = 'mock_operation', slicer.table.abc
        mock_operation.metrics = []

        mock_widget = f.Widget(mock_operation)
        mock_widget.transform = Mock()

        mock_df = {}
        mock_fetch_data.return_value = mock_df

        # Need to keep widget the last call in the chain otherwise the object gets cloned and the assertion won't work
        slicer.data \
            .dimension(slicer.dimensions.timestamp) \
            .widget(mock_widget) \
            .fetch()

        f_op_key = format_metric_key(mock_operation.key)
        self.assertIn(f_op_key, mock_df)
        self.assertEqual(mock_df[f_op_key], mock_operation.apply.return_value)
