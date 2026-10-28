"""Public workbench actions expose detached evidence only."""
from test_support.contracts.observations import observed
from test_support.physical import backend as _driver


@observed
def inspect_workbench():
    return _driver.inspect_workbench()


@observed
def run_and_review():
    return _driver.run_and_review()


@observed
def check_admission():
    return _driver.check_admission()


@observed
def restart_workbench():
    return _driver.restart_workbench()


@observed
def recover_abandoned_run():
    return _driver.recover_abandoned_run()


@observed
def stop_execution():
    return _driver.stop_execution()


@observed
def import_evidence():
    return _driver.import_evidence()


@observed
def corrupt_archive():
    return _driver.corrupt_archive()


@observed
def exercise_http():
    return _driver.exercise_http()


@observed
def run_independently():
    return _driver.run_independently()


@observed
def recover_forged_quality():
    return _driver.recover_forged_quality()


@observed
def reject_invalid_contract():
    return _driver.reject_invalid_contract()


@observed
def review_other_report_shape():
    return _driver.review_other_report_shape()


@observed
def run_second_system():
    return _driver.run_second_system()


@observed
def stop_second_system():
    return _driver.stop_second_system()


@observed
def check_cli_authentication():
    return _driver.check_cli_authentication()


@observed
def retry_failed_review_write():
    return _driver.retry_failed_review_write()
