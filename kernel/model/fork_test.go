package model

import (
	"testing"

	"github.com/siyuan-note/siyuan/kernel/conf"
)

func TestForkUpdaterIgnoresExistingDownloadPreference(t *testing.T) {
	originalConf := Conf
	Conf = NewAppConf()
	Conf.System = conf.NewSystem()
	t.Cleanup(func() { Conf = originalConf })
	Conf.System.DownloadInstallPkg = true
	if !skipNewVerInstallPkg() {
		t.Fatal("fork must not download upstream installers even with an existing enabled preference")
	}
	if getNewVerInstallPkgPath() != "" {
		t.Fatal("fork must not install a cached upstream package")
	}
}
