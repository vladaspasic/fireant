from collections import defaultdict

from toposort import (
    CircularDependencyError,
    toposort_flatten,
)

from fireant.utils import (
    immutable,
    ordered_distinct_list,
    ordered_distinct_list_by_attr,
)
from .database import fetch_data
from .references import join_reference
from ..dimensions import RollupDimension
from ..exceptions import (
    CircularJoinsException,
    MissingTableJoinException,
    RollupException,
)
from ..filters import DimensionFilter
from ..intervals import DatetimeInterval
from ..operations import Operation


def _build_dimension_definition(dimension, interval_func):
    if hasattr(dimension, 'interval') and isinstance(dimension.interval, DatetimeInterval):
        return interval_func(dimension.definition,
                             dimension.interval).as_(dimension.key)

    return dimension.definition.as_(dimension.key)


def _select_groups(terms, query, rollup, database):
    query = query.select(*terms)

    if not rollup:
        return query.groupby(*terms)

    if 1 < len(terms):
        # This step packs multiple terms together so that they are rolled up together. This is needed for unique
        # dimensions to keep the display field grouped together with the definition field.
        terms = [terms]

    return database.totals(query, terms)


def is_rolling_up(dimension, rolling_up):
    if rolling_up:
        if not isinstance(dimension, RollupDimension):
            raise RollupException('Cannot roll up dimension {}'.format(dimension))
        return True
    return getattr(dimension, "is_rollup", False)


def clean(index):
    import pandas as pd

    if isinstance(index, (pd.DatetimeIndex, pd.RangeIndex)):
        return index

    return index.astype('str')


def clean_index(data_frame):
    import pandas as pd

    if hasattr(data_frame.index, 'levels'):
        data_frame.index = pd.MultiIndex(
              levels=[level.astype('str')
                      if not isinstance(level, (pd.DatetimeIndex, pd.RangeIndex))
                      else level
                      for level in data_frame.index.levels],
              labels=data_frame.index.labels
        )

    elif not isinstance(data_frame.index, (pd.DatetimeIndex, pd.RangeIndex)):
        data_frame.index = data_frame.index.astype('str')

    return data_frame


class QueryBuilder(object):
    """

    """

    def __init__(self, slicer):
        self.slicer = slicer
        self._widgets = []
        self._dimensions = []
        self._filters = []
        self._orders = []

    @immutable
    def widget(self, *widgets):
        """

        :param widgets:
        :return:
        """
        self._widgets += widgets

    @immutable
    def dimension(self, *dimensions):
        """

        :param dimensions:
        :return:
        """
        self._dimensions += dimensions

    @immutable
    def filter(self, *filters):
        """
        :param filters:
        :return:
        """
        self._filters += filters

    @property
    def tables(self):
        """
        :return:
            A collection of tables required to execute a query,
        """
        return ordered_distinct_list([table
                                      for group in [self.metrics, self._dimensions, self._filters]
                                      for element in group
                                      for attr in [getattr(element, 'definition', None),
                                                   getattr(element, 'display_definition', None)]
                                      if attr is not None
                                      for table in attr.tables_])

    @property
    def metrics(self):
        """
        :return:
            an ordered, distinct list of metrics used in all widgets as part of this query.
        """
        return ordered_distinct_list_by_attr([metric
                                              for widget in self._widgets
                                              for metric in widget.metrics])

    @property
    def operations(self):
        """
        :return:
            an ordered, distinct list of metrics used in all widgets as part of this query.
        """
        return ordered_distinct_list_by_attr([metric
                                              for widget in self._widgets
                                              for metric in widget.metrics
                                              if isinstance(metric, Operation)])

    @property
    def joins(self):
        """
        Given a set of tables required for a slicer query, this function finds the joins required for the query and
        sorts them topologically.

        :return:
            A list of joins in the order that they must be joined to the query.
        :raises:
            MissingTableJoinException - If a table is required but there is no join for that table
            CircularJoinsException - If there is a circular dependency between two or more joins
        """
        dependencies = defaultdict(set)
        slicer_joins = {join.table: join
                        for join in self.slicer.joins}
        tables_to_eval = list(self.tables)

        while tables_to_eval:
            table = tables_to_eval.pop()

            if self.slicer.table == table:
                continue

            if table not in slicer_joins:
                raise MissingTableJoinException('Could not find a join for table {table}'
                                                .format(table=str(table)))

            join = slicer_joins[table]
            tables_required_for_join = set(join.criterion.tables_) - {self.slicer.table, join.table}

            dependencies[join] |= {slicer_joins[table]
                                   for table in tables_required_for_join}
            tables_to_eval += tables_required_for_join - {d.table for d in dependencies}

        try:
            return toposort_flatten(dependencies)
        except CircularDependencyError as e:
            raise CircularJoinsException(str(e))

    @property
    def query(self):
        """
        WRITEME
        """
        query = self.slicer.database.query_cls.from_(self.slicer.table)

        # Add joins
        for join in self.joins:
            query = query.join(join.table, how=join.join_type).on(join.criterion)

        # Add dimensions
        rolling_up = False
        for dimension in self._dimensions:
            rolling_up = is_rolling_up(dimension, rolling_up)

            dimension_definition = _build_dimension_definition(dimension, self.slicer.database.trunc_date)

            if hasattr(dimension, 'display_definition'):
                # Add display definition field
                dimension_display_definition = dimension.display_definition.as_(dimension.display_key)
                fields = [dimension_definition, dimension_display_definition]

            else:
                fields = [dimension_definition]

            query = _select_groups(fields, query, rolling_up, self.slicer.database)

        # Add metrics
        query = query.select(*[metric.definition.as_(metric.key)
                               for metric in self.metrics])

        # Add filters
        for filter_ in self._filters:
            query = query.where(filter_.definition) \
                if isinstance(filter_, DimensionFilter) \
                else query.having(filter_.definition)

        # Add references
        references = [(reference, dimension)
                      for dimension in self._dimensions
                      if hasattr(dimension, 'references')
                      for reference in dimension.references]
        if references:
            query = self._join_references(query, references)

        # Add ordering
        order = self._orders if self._orders else self._dimensions
        query = query.orderby(*[element.definition.as_(element.key)
                                for element in order])

        return str(query)

    def _join_references(self, query, references):
        original_query = query.as_('base')

        def original_query_field(key):
            return original_query.field(key).as_(key)

        outer_query = self.slicer.database.query_cls.from_(original_query)

        # Add dimensions
        for dimension in self._dimensions:
            outer_query = outer_query.select(original_query_field(dimension.key))

            if hasattr(dimension, 'display_definition'):
                outer_query = outer_query.select(original_query_field(dimension.display_key))

        # Add metrics
        outer_query = outer_query.select(*[original_query_field(metric.key)
                                           for metric in self.metrics])

        # Build nested reference queries
        for reference, dimension in references:
            outer_query = join_reference(reference,
                                         self.metrics,
                                         self._dimensions,
                                         dimension,
                                         self.slicer.database.date_add,
                                         original_query,
                                         outer_query)

        return outer_query

    def render(self):
        """

        :return:
        """
        query = self.query

        data_frame = fetch_data(self.slicer.database,
                                query,
                                dimensions=self._dimensions)

        # Apply operations
        for operation in self.operations:
            data_frame[operation.key] = operation.apply(data_frame)

        # Apply transformations
        return [widget.transform(data_frame, self.slicer, self._dimensions)
                for widget in self._widgets]

    def __str__(self):
        return self.query

    def __iter__(self):
        return iter(self.render())
