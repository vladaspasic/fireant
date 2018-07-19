from pypika.terms import (
    Case,
    NullValue,
    ValueWrapper,
)
from typing import Iterable

from fireant.utils import immutable
from .base import SlicerElement
from .exceptions import QueryException
from .filters import (
    BooleanFilter,
    ContainsFilter,
    ExcludesFilter,
    NotLikeFilter,
    PatternFilter,
    RangeFilter,
)
from .intervals import (
    NumericInterval,
    daily,
)


class Dimension(SlicerElement):
    """
    The `Dimension` class represents a dimension in the `Slicer` object.
    """

    def __init__(self, key, label=None, definition=None, display_definition=None):
        super(Dimension, self).__init__(key, label, definition, display_definition)
        self.is_rollup = False

    @immutable
    def rollup(self):
        """
        Configures this dimension and all subsequent dimensions in a slicer query to be rolled up to provide the totals.
        This will include an extra value for each pair of dimensions labeled `Totals`. which will include the totals for
        the group.
        """
        self.is_rollup = True

    def __repr__(self):
        return "slicer.dimensions.{}".format(self.key)


class BooleanDimension(Dimension):
    """
    This is a dimension that represents a boolean true/false value.  The expression should always result in a boolean
    value.
    """

    def __init__(self, key, label=None, definition=None):
        super(BooleanDimension, self).__init__(key,
                                               label,
                                               definition)

    def is_(self, value: bool):
        """
        Creates a filter to filter a slicer query.

        :param value:
            True or False
        :return:
            A slicer query filter used to filter a slicer query to results where this dimension is True or False.
        """
        return BooleanFilter(self.definition, value)


class PatternFilterableMixin:
    definition = None
    pattern_definition_attribute = 'definition'

    def like(self, pattern, *patterns):
        """
        Creates a filter to filter a slicer query.

        :param pattern:
            A pattern to match against the dimension's display definition.  This pattern is used in the SQL query as
            the `LIKE` expression.
        :param patterns:
            Additional patterns. This is the same as the pattern argument. The function signature is intended to
            syntactically require at least one pattern.
        :return:
            A slicer query filter used to filter a slicer query to results where this dimension's display definition
            matches the pattern.
        """
        return PatternFilter(getattr(self, self.pattern_definition_attribute), pattern, *patterns)

    def not_like(self, pattern, *patterns):
        """
        Creates a filter to filter a slicer query.

        :param pattern:
            A pattern to match against the dimension's display definition.  This pattern is used in the SQL query as
            the `NOT LIKE` expression.
        :param patterns:
            Additional patterns. This is the same as the pattern argument. The function signature is intended to
            syntactically require at least one pattern.
        :return:
            A slicer query filter used to filter a slicer query to results where this dimension's display definition
            matches the pattern.
        """
        return NotLikeFilter(getattr(self, self.pattern_definition_attribute), pattern, *patterns)


class CategoricalDimension(PatternFilterableMixin, Dimension):
    """
    This is a dimension that represents an enum-like database field, with a finite list of options to chose from. It
    provides support for configuring a display value for each of the possible values.
    """

    def __init__(self, key, label=None, definition=None, display_values=()):
        super(CategoricalDimension, self).__init__(key,
                                                   label,
                                                   definition)
        self.display_values = dict(display_values)

    def isin(self, values: Iterable):
        """
        Creates a filter to filter a slicer query.

        :param values:
            An iterable of value to constrain the slicer query results by.

        :return:
            A slicer query filter used to filter a slicer query to results where this dimension is one of a set of
            values. Opposite of #notin.
        """
        return ContainsFilter(self.definition, values)

    def notin(self, values):
        """
        Creates a filter to filter a slicer query.

        :param values:
            An iterable of value to constrain the slicer query results by.

        :return:
            A slicer query filter used to filter a slicer query to results where this dimension is *not* one of a set of
            values. Opposite of #isin.
        """
        return ExcludesFilter(self.definition, values)


class _UniqueDimensionBase(PatternFilterableMixin, Dimension):
    def isin(self, values, use_display=False):
        """
        Creates a filter to filter a slicer query.

        :param values:
            An iterable of value to constrain the slicer query results by.
        :param use_display:
            When True, the filter will be applied to the Dimesnion's display definition instead of the definition.

        :return:
            A slicer query filter used to filter a slicer query to results where this dimension is one of a set of
            values. Opposite of #notin.
        """
        if use_display and self.display_definition is None:
            raise QueryException('No value set for display_definition.')
        filter_field = self.display_definition if use_display else self.definition
        return ContainsFilter(filter_field, values)

    def notin(self, values, use_display=False):
        """
        Creates a filter to filter a slicer query.

        :param values:
            An iterable of value to constrain the slicer query results by.
        :param use_display:
            When True, the filter will be applied to the Dimesnion's display definition instead of the definition.

        :return:
            A slicer query filter used to filter a slicer query to results where this dimension is *not* one of a set of
            values. Opposite of #isin.
        """
        if use_display and self.display_definition is None:
            raise QueryException('No value set for display_definition.')
        filter_field = self.display_definition if use_display else self.definition
        return ExcludesFilter(filter_field, values)


class UniqueDimension(_UniqueDimensionBase):
    """
    This is a dimension that represents a field in a database which is a unique identifier, such as a primary/foreign
    key. It provides support for a display value field which is selected and used in the results.
    """
    pattern_definition_attribute = 'display_definition'

    def __init__(self, key, label=None, definition=None, display_definition=None):
        super(UniqueDimension, self).__init__(key,
                                              label,
                                              definition,
                                              display_definition)

    def __hash__(self):
        if self.has_display_field:
            return hash('{}({},{})'.format(self.__class__.__name__, self.definition, self.display_definition))
        return super(UniqueDimension, self).__hash__()

    @property
    def display(self):
        return self

    def like(self, pattern, *patterns):
        if self.display_definition is None:
            raise QueryException('No value set for display_definition.')
        return super(UniqueDimension, self).like(pattern, *patterns)

    def not_like(self, pattern, *patterns):
        if self.display_definition is None:
            raise QueryException('No value set for display_definition.')
        return super(UniqueDimension, self).not_like(pattern, *patterns)


class DisplayDimension(_UniqueDimensionBase):
    """
    WRITEME
    """

    def __init__(self, dimension):
        super(DisplayDimension, self).__init__(dimension.display_key,
                                               dimension.label,
                                               dimension.display_definition)


class ContinuousDimension(Dimension):
    """
    This is a dimension that represents a field in the database which is a continuous value, such as a decimal, integer,
    or date/time. It requires the use of an interval which is the window over the values.
    """

    def __init__(self, key, label=None, definition=None, default_interval=NumericInterval(1, 0)):
        super(ContinuousDimension, self).__init__(key,
                                                  label,
                                                  definition)
        self.interval = default_interval


class DatetimeDimension(ContinuousDimension):
    """
    A subclass of ContinuousDimension which reflects a date/time data type. Intervals are replaced with time intervals
    such as daily, weekly, annually, etc.  A reference can be used to show a comparison over time such as
    week-over-week or month-over-month.
    """

    def __init__(self, key, label=None, definition=None, default_interval=daily):
        super(DatetimeDimension, self).__init__(key,
                                                label,
                                                definition,
                                                default_interval=default_interval)

    @immutable
    def __call__(self, interval):
        """
        When calling a datetime dimension an interval can be supplied:

        ```
        from fireant import weekly

        my_slicer.dimensions.date # Daily interval used as default
        my_slicer.dimensions.date(weekly) # Daily interval used as default
        ```

        :param interval:
            An interval to use with the dimension.  See `fireant.intervals`.
        :return:
            A copy of the dimension with the interval set.
        """
        self.interval = interval

    def between(self, start, stop):
        """
        Creates a filter to filter a slicer query.

        :param start:
            The start time of the filter. This is the beginning of the window for which results should be included.
        :param stop:
            The stop time of the filter. This is the end of the window for which results should be included.
        :return:
            A slicer query filter used to filter a slicer query to results where this dimension is between the values
            start and stop.
        """
        return RangeFilter(self.definition, start, stop)


class PatternDimension(PatternFilterableMixin, Dimension):
    """
    This is a dimension that represents a boolean true/false value.  The expression should always result in a boolean
    value.
    """
    pattern_definition_attribute = 'field'
    _DEFAULT = ValueWrapper('No Group')

    def __init__(self, key, label=None, definition=None):
        super(PatternDimension, self).__init__(key,
                                               label,
                                               self._DEFAULT)
        self.field = definition

    @immutable
    def __call__(self, groups):
        """
        When calling a datetime dimension an interval can be supplied:

        ```
        from fireant import weekly

        my_slicer.dimensions.date # Daily interval used as default
        my_slicer.dimensions.date(weekly) # Daily interval used as default
        ```

        :param interval:
            An interval to use with the dimension.  See `fireant.intervals`.
        :return:
            A copy of the dimension with the interval set.
        """
        self.groups = groups

        cases = Case()
        for group in groups:
            cases = cases.when(self.field.like(group), group)

        self.definition = cases.else_(self._DEFAULT)

    def __repr__(self):
        dimension = super().__repr__()

        if self.groups is not None:
            return '{}({})'.format(dimension, self.groups)

        return dimension


class TotalsDimension(Dimension):
    def __init__(self, dimension):
        totals_definition = NullValue()
        display_definition = totals_definition \
            if dimension.has_display_field \
            else None

        super(TotalsDimension, self).__init__(dimension.key,
                                              dimension.label,
                                              totals_definition,
                                              display_definition)
