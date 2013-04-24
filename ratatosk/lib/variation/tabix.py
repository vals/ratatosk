# Copyright (c) 2013 Per Unneberg
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
"""
Provide wrappers for `tabix <http://sourceforge.net/projects/samtools/files/tabix/>`_


Classes
-------
"""

import os
import luigi
import ratatosk.lib.files.input
from ratatosk.job import JobTask, JobWrapperTask
from ratatosk.jobrunner import DefaultShellJobRunner
from ratatosk.utils import rreplace, fullclassname
from ratatosk.log import get_logger

logger = get_logger()

class InputVcfFile(ratatosk.lib.files.input.InputVcfFile):
    pass

class TabixJobRunner(DefaultShellJobRunner):
    pass

class TabixJobTask(JobTask):
    executable = ""

    def job_runner(self):
        return TabixJobRunner()

    def exe(self):
        return self.sub_executable
    
    def main(self):
        return None

class Bgzip(TabixJobTask):
    sub_executable = luigi.Parameter(default="bgzip")
    parent_task = luigi.Parameter(default="ratatosk.lib.variation.tabix.InputVcfFile")
    suffix = luigi.Parameter(default=".vcf.gz")
    options = luigi.Parameter(default=("-f",))

    def args(self):
        return [self.input()[0]]

# Since this is such a common operation, add the task here
class BgUnzip(TabixJobTask):
    sub_executable = luigi.Parameter(default="bgzip")
    parent_task = luigi.Parameter(default="ratatosk.lib.variation.tabix.Bgzip")
    suffix = luigi.Parameter(default=".vcf")

    def opts(self):
        retval = list(self.options)
        if not "-d" in retval:
            retval += ["-d"]
        return retval

    def args(self):
        return [self.input()[0]]

class Tabix(TabixJobTask):
    sub_executable = luigi.Parameter(default="tabix")
    parent_task = luigi.Parameter(default="ratatosk.lib.variation.tabix.Bgzip")
    suffix = luigi.Parameter(default=".vcf.gz.tbi")

    def args(self):
        return [self.input()[0]]
    

class IndexedBgzip(JobWrapperTask):
    suffix = luigi.Parameter(default=(".vcf.gz", ".vcf.gz.tbi"), is_list=True)
    parent_task = luigi.Parameter(default="ratatosk.lib.variation.tabix.Bgzip")

    def requires(self):
        zipcls = ratatosk.lib.variation.tabix.Bgzip
        indexcls = ratatosk.lib.variation.tabix.Tabix
        return [zipcls(target=self.source()[0]), 
                       indexcls(target=rreplace(self.source()[0], zipcls().sfx(), indexcls().sfx(), 1),
                                parent_task=fullclassname(zipcls))]

