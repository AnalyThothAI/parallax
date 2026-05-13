usage: gmgn-twitter-intel [-h]
                          {serve,init,config,db,recent,search,asset-flow,account-alerts,account-quality,social-events,attention-seeds,harness-snapshots,harness-outcomes,harness-credits,harness-weights,harness-score-buckets,harness-health,enrichment-jobs,notification-deliveries,ops} ...

positional arguments:
  {serve,init,config,db,recent,search,asset-flow,account-alerts,account-quality,social-events,attention-seeds,harness-snapshots,harness-outcomes,harness-credits,harness-weights,harness-score-buckets,harness-health,enrichment-jobs,notification-deliveries,ops}
    serve               run the collector service
    init                create ~/.gmgn-twitter-intel/config.yaml
    config              print effective runtime configuration
    db                  database lifecycle commands
    recent              print recent stored events
    search              search stored tweets by query text
    asset-flow          rank resolved assets and unresolved attention
                        candidates
    account-alerts      print watched-account token alerts
    account-quality     print account quality profiles
    social-events       print harness social event read model
    attention-seeds     print harness attention seeds
    harness-snapshots   print harness snapshots
    harness-outcomes    print harness outcomes
    harness-credits     print harness credits
    harness-weights     print harness weights
    harness-score-buckets
                        print harness score bucket report
    harness-health      print harness health summary
    enrichment-jobs     inspect social-event extraction job backlog
    notification-deliveries
                        inspect notification external delivery audit rows
    ops                 maintenance commands

options:
  -h, --help            show this help message and exit
