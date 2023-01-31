def refresh(c: DuneClient, query: Query, ping_frequency: int = 5):
        """
        Executes a Dune `query`, waits until execution completes,
        fetches and returns the results.
        Sleeps `ping_frequency` seconds between each status request.
        """
        job_id = c.execute(query).execution_id
        while c.get_status(job_id).state != ExecutionState.COMPLETED:
            time.sleep(ping_frequency)

        return c.get_result(job_id).result