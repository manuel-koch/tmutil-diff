# Analyze differences between consecutive Time Machine backups

This tool requires `Full Disk Access` to query __Time Machine__ information!

The script will open __Finder__ for the selected backup directories
on the __Time Machine__ volume, otherwise those directories don't seem to be available!?
Sometimes you will need to open a __Finder__ window manually for a specific backup directory.
Keep the __Finder__ windows open while the script runs!

Plugin your __Time Machine__ volume and run the script.

I used the script to analyze big backups on my Macbook Pro
running Sequoia 15.5 with a Time Machine disk attached via USB.

# Examples

Run the script without any arguments to see all available backups
of current users home directory:

```shell
tmutil-diff.py
```

Select a backup index you want to analyze and run the script again:
You can use negative index to denote the last nth backup, e.g. -1 is the last backup.

Analyzing can take some time!

The result of the analysis will only contain changes for directories!
But this can be used to identify directories that likely spam your backups with
too many/big or too frequent changes.

```shell
# show all changes between last backup and its predecessor
tmutil-diff.py --backup-idx -1
```

```shell
# show only the nth greatest changes between selected index and its predecessor
tmutil-diff.py --backup-idx 5 --order SIZE --limit 50
```

# Usage / Help

```shell
$ tmutil-diff.py --help
usage: tmutil-diff.py [-h] [--backup-idx IDX] [--order {PATH,SIZE}] [--limit LIMIT] [--cache PATH]

Analyse differences between Time Machine backups.

options:
  -h, --help           show this help message and exit
  --backup-idx IDX     Analyse backup at index with its predecessor. Default will just show all available backups.
  --order {PATH,SIZE}  Order output of changes by selected criteria.
  --limit LIMIT        Only output up to given number of changes.
  --cache PATH         Use given directory to cache disk usage details of backups. Default is '$HOME/tmp'.
```

