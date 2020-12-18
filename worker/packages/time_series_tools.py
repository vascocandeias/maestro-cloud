import argparse
import csv
import re
import sys
import math
# force module path to be able to be called with subprocess from lambda
sys.path.insert(1, '/opt/python')
import pandas

names = {
    "eqw": "discrete.csv",
    "eqf": "discrete.csv",
    "lr": "imputed.csv",
    "locf": "imputed.csv"
}


def getTimeSeries(name, method):
    data = pandas.read_csv(name, na_values=['?'])

    headers = data.columns
    attributes = list(headers)
    attributes.pop(0)

    firstIndex = int(attributes[0].rpartition('__')[2])
    lastIndex = int(attributes[len(attributes) - 1].rpartition('__')[2])

    numTimeSlices = lastIndex - firstIndex + 1

    if len(attributes) % numTimeSlices != 0:
        sys.exit("Malformatted header")

    numAttributes = int(len(attributes) / numTimeSlices)

    attributes = [v.rpartition('__')[0] for v in attributes[0:numAttributes]]

    for attribute in attributes:
        regex = re.compile(attribute + '__[0-9]+$')
        cols = list(filter(regex.match, headers))
        data[cols] = method(data[cols].transpose(), attribute).transpose().fillna(
            "").astype(str).replace(to_replace="\.0+$", value="", regex=True)

    return data


def getLabel(number):
    return (getLabel(math.floor(number / 26) - 1) if number >= 26 else '') + 'abcdefghijklmnopqrstuvwxyz'[number % 26]


def locf(timeSeries, attribute): return timeSeries.ffill().bfill()


def lr(timeSeries, attribute): return timeSeries.interpolate(limit_direction='both')


def eqf(timeSeries, attribute, nBins, discrete):
    if attribute in discrete:
        return timeSeries
    labels = {}
    for x in range(nBins):
        labels[x] = getLabel(x)
    timeSeries = timeSeries.stack()
    return pandas.qcut(timeSeries, nBins, labels=False, duplicates='drop').map(labels).unstack() if nBins < timeSeries.nunique() else timeSeries.unstack()


def eqw(timeSeries, attribute, nBins, discrete):
    if attribute in discrete:
        return timeSeries
    labels = {}
    for x in range(nBins):
        labels[x] = getLabel(x)
    timeSeries = timeSeries.stack()
    return pandas.cut(timeSeries, nBins, labels=False, duplicates='drop').map(labels).unstack() if nBins < timeSeries.nunique() else timeSeries.unstack()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter,
                                     description='Discretization and imputation of multivariate time series.', add_help=False)

    arguments = parser.add_argument_group('Arguments')
    arguments.add_argument('method', metavar="method", type=str.lower, choices=['locf', 'lr', 'eqw', 'eqf'], help='''Method to use. Can be one of the following.\n
For imputation:\n
locf - Use last obervation. If no previous observation, use next one.\n
lr - Interpolate with linear regression.\n
For discretization:\n
eqw - Use bins with equal width.\n
eqf - Try to create bins with the same number of observations.\n\n''')

    arguments.add_argument('-i', required=True, metavar="<file_path>",
                           help='Path to the input CSV file to be used.\n\n')

    arguments.add_argument('-n', default=2, type=int, metavar="<int>",
                           help='Number of bins to use in discretization. Defaults to 2.\n\n')

    arguments.add_argument('-d', default=[], nargs="*", metavar="<string>",
                           help='List of discrete attributes to skip discretization. Defaults to [].\n\n')

    arguments.add_argument('-h', action='help',
                           help='Show this help message and exit.\n\n')

    args = parser.parse_args()

    if args.method == 'locf':
        function = locf
    elif args.method == 'lr':
        function = lr
    elif args.method == 'eqw':
        def function(timeSeries, attribute): return eqw(timeSeries, attribute, args.n, args.d)
    elif args.method == 'eqf':
        def function(timeSeries, attribute): return eqf(timeSeries, attribute, args.n, args.d)
    else:
        raise ValueError('Method not supported')

    timeSeries = getTimeSeries(args.i, function)
    timeSeries.to_csv(names[args.method], index=False)
