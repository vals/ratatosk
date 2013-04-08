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
import os
import re
import luigi
import time
import shutil
from ratatosk.job import InputJobTask, JobTask, JobWrapperTask, DefaultShellJobRunner, PipedTask
from ratatosk.lib.tools.samtools import SamToBam
from ratatosk.utils import rreplace, fullclassname
from cement.utils import shell

class BwaJobRunner(DefaultShellJobRunner):
    pass

class InputFastqFile(InputJobTask):
    _config_section = "bwa"
    _config_subsection = "InputFastqFile"
    parent_task = luigi.Parameter(default="ratatosk.lib.files.external.FastqFile")
    suffix = luigi.Parameter(default=".fastq.gz")

class InputFastaFile(InputJobTask):
    _config_section = "bwa"
    _config_subsection = "InputFastaFile"
    parent_task = luigi.Parameter(default="ratatosk.lib.files.external.FastaFile")
    suffix = luigi.Parameter(default=".fa")

class BwaJobTask(JobTask):
    """Main bwa class with parameters necessary for all bwa classes"""
    _config_section = "bwa"
    executable = luigi.Parameter(default="bwa")
    bwaref = luigi.Parameter(default=None)
    num_threads = luigi.Parameter(default=1)

    def job_runner(self):
        return BwaJobRunner()

    def output(self):
        return luigi.LocalTarget(self.target)


class Aln(BwaJobTask):
    _config_subsection = "Aln"
    sub_executable = "aln"
    parent_task = luigi.Parameter(default=("ratatosk.lib.align.bwa.InputFastqFile",))
    suffix = luigi.Parameter(default=".sai")
    read1_suffix = luigi.Parameter(default="_R1_001")
    read2_suffix = luigi.Parameter(default="_R2_001")
    is_read1 = True
    can_multi_thread = True

    def opts(self):
        # Threads is an option so handle it here
        retval = list(self.options)
        return retval + ['-t {}'.format(str(self.threads()))]

    def requires(self):
        cls = self.parent()[0]
        source = self.source()[0]
        # Ugly hack for 1 -> 2 dependency: works but should be dealt with otherwise
        if str(fullclassname(cls)) in ["ratatosk.lib.utils.misc.ResyncMatesJobTask"]:
            if re.search(self.read1_suffix, source):
                self.is_read1 = True
                fq1 = source
                fq2 = rreplace(source, self.read1_suffix, self.read2_suffix, 1)
            else:
                self.is_read1 = False
                fq1 = rreplace(source, self.read2_suffix, self.read1_suffix, 1)
                fq2 = source
            return cls(target=[fq1, fq2])
        else:
            return cls(target=source)

    def args(self):
        # bwa aln "-f" option seems to be broken!?!
        if isinstance(self.input(), list):
            if self.is_read1:
                return [self.bwaref, self.input()[0], ">", self.output()]
            else:
                return [self.bwaref, self.input()[1], ">", self.output()]
        else:
            return [self.bwaref, self.input(), ">", self.output()]

class BwaAlnWrapperTask(JobWrapperTask):
    fastqfiles = luigi.Parameter(default=[], is_list=True)
    def requires(self):
        return [Aln(target=x) for x in self.fastqfiles]

class Sampe(BwaJobTask):
    _config_subsection = "Sampe"
    sub_executable = "sampe"
    # Get these with static methods
    add_label = luigi.Parameter(default=("_R1_001", "_R2_001"), is_list=True)
    suffix = luigi.Parameter(default=".sam")
    read_group = luigi.Parameter(default=None)
    platform = luigi.Parameter(default="Illumina")
    parent_task = luigi.Parameter(default=("ratatosk.lib.align.bwa.Aln", "ratatosk.lib.align.bwa.Aln"), is_list=True)
    can_multi_thread = False
    max_memory_gb = 6 # bwa documentation says ~5.4 for human genome

    def _get_read_group(self):
        if not self.read_group:
            from ratatosk import backend
            cls = self.parent()[0]
            sai1 = self.input()[0]
            rgid = rreplace(rreplace(sai1.path, cls().suffix, "", 1), self.add_label[0], "", 1)
            smid = rgid
            # Get sample information if present in global vars. Note
            # that this requires the
            # backend.__global_vars__["targets"] be set
            # This is not perfect but works for now
            for tgt in backend.__global_vars__.get("targets", []):
                if smid.startswith(tgt[2]):
                    smid = tgt[0]
                    break
            # The platform should be configured elsewhere
            rg = "\"{}\"".format("\t".join(["@RG", "ID:{}".format(rgid), "SM:{}".format(smid), "PL:{}".format(self.platform)]))
            if self.pipe:
                return rg.replace("\t", "\\t")
            else:
                return rg
        else:
            return self.read_group

    def args(self):
        cls = self.parent()[0]
        parent_cls = cls().parent()[0]
        (fastq1, fastq2) = [luigi.LocalTarget(rreplace(sai.path, cls().suffix, parent_cls().sfx(), 1)) for sai in self.input()]
        return ["-r", self._get_read_group(), self.bwaref, self.input()[0].path, self.input()[1].path, fastq1, fastq2, ">", self.output()]

class Bampe(PipedTask):
    _config_section = "bwa"
    _config_subsection = "Bampe"
    add_label = luigi.Parameter(default=("_R1_001", "_R2_001"), is_list=True)
    parent_task = luigi.Parameter(default=("ratatosk.lib.align.bwa.Aln", "ratatosk.lib.align.bwa.Aln"), is_list=True)
    suffix = luigi.Parameter(default=".bam")
    read_group = luigi.Parameter(default=None)
    platform = luigi.Parameter(default="Illumina")
    can_multi_thread = False
    max_memory_gb = 6 # bwa documentation says ~5.4 for human genome

    def args(self):
        return [Sampe(target=self.target.replace(".bam", ".sam"), pipe=True), SamToBam(target=self.target, pipe=True)]

class Index(BwaJobTask):
    _config_subsection = "index"
    sub_executable = "index"
    suffix = luigi.Parameter(default=".fa.bwt")
    parent_task = luigi.Parameter(default=("ratatosk.lib.align.bwa.InputFastaFile", ), is_list=True)
    
    def args(self):
        return [self.input()[0]]
