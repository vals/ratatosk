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
Provide wrappers for `htslib <https://github.com/samtools/htslib>`_

Make a link from `vcf` to `htscmd` to use the shortcut commands.


Classes
-------
"""

import luigi
import ratatosk.lib.files.input
import ratatosk.lib.variation.tabix
from ratatosk.handler import RatatoskHandler, register_task_handler
from ratatosk.job import JobTask
from ratatosk.jobrunner import  DefaultShellJobRunner
from ratatosk.utils import rreplace, fullclassname
from ratatosk.log import get_logger

logger = get_logger()

class InputVcfFile(ratatosk.lib.files.input.InputVcfFile):
    pass

class HtslibJobRunner(DefaultShellJobRunner):
    pass

class HtslibVcfJobTask(JobTask):
    executable = luigi.Parameter(default="vcf")
    parent_task = luigi.Parameter(default=("ratatosk.lib.variation.htslib.InputVcfFile", ), is_list=True)

    def job_runner(self):
        return HtslibJobRunner()

class HtslibIndexedVcfJobTask(HtslibVcfJobTask):
    def requires(self):
        vcfcls = self.parent()[0]
        indexcls = ratatosk.lib.variation.tabix.Tabix
        return [cls(target=source) for cls, source in izip(self.parent(), self.source())] + [indexcls(target=rreplace(self.source()[0], vcfcls().suffix, indexcls().suffix, 1), parent_task=fullclassname(vcfcls))]

class VcfMerge(HtslibIndexedVcfJobTask):
    sub_executable = luigi.Parameter(default="merge")
    target_generator_handler = luigi.Parameter(default=None)
    label = luigi.Parameter(default=".vcfmerge")
    suffix = luigi.Parameter(default=".vcf")
    parent_task = luigi.Parameter(default=("ratatosk.lib.variation.tabix.IndexedBgzip", ), is_list=True)

    def args(self):
        return [x for x in self.input()] + [">", self.output()]
    
    def requires(self):
        cls = self.parent()[0]
        sources = []
        if self.target_generator_handler and "target_generator_handler" not in self._handlers.keys():
            tgf = RatatoskHandler(label="target_generator_handler", mod=self.target_generator_handler)
            register_task_handler(self, tgf)
        if not "target_generator_handler" in self._handlers.keys():
            logging.warn("vcf merge requires a target generator handler; no defaults are as of yet implemented")
            return []
        sources = self._handlers["target_generator_handler"](self)
        return [cls(target=src) for src in sources]
