"""
Provide wrappers for bcftools

Classes
-------
"""
import luigi
from ratatosk.job import InputJobTask, JobTask, DefaultShellJobRunner


class BcfJobRunner(DefaultShellJobRunner):
    pass


class InputBcfFile(InputJobTask):
    parent_task = luigi.Parameter(default="ratatosk.lib.files.external.BcfFile")
    target_suffix = luigi.Parameter(default=".bcf")


class BcftoolsJobTask(JobTask):
    """Main bcftools job task
    """
    executable = luigi.Parameter(default="bcftools")
    parent_task = luigi.Parameter(default=("ratatosk.lib.variation.bcftools.InputBcfFile", ), is_list=True)

    def job_runner(self):
        return BcfJobRunner()


class SNPCalling(BcftoolsJobTask):
    sub_executable = "view"
    options = luigi.Parameter(default=("-c",), is_list=True)
    suffix = luigi.Parameter(default=".vcf")

    def args(self):
        retval = [self.input()[0], ">", self.output()]
        if self.pipe:
            return retval + ["-"]

        return retval
