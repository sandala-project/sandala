class StorageQueryRejectedError(Exception):
    """A storage query was rejected; its message is safe for service callers.

    Repositories expose this storage-level contract without driver-specific
    details. Unclassified storage failures use their original exceptions instead.
    """
