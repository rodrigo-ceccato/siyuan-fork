// SiYuan - From thought to insight, with agents
// Copyright (c) 2020-present, b3log.org
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Affero General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.

package model

import (
	"testing"

	"github.com/siyuan-note/siyuan/kernel/conf"
)

func TestCheckSyncPreservesEnabledWithoutUser(t *testing.T) {
	originalConf := Conf
	Conf = NewAppConf()
	Conf.Sync = conf.NewSync()
	Conf.Sync.Provider = conf.ProviderSiYuan
	Conf.Sync.Enabled = true
	t.Cleanup(func() {
		Conf = originalConf
	})

	if checkSync(false, false, true) {
		t.Fatal("sync must not start without a user")
	}
	if !Conf.Sync.Enabled {
		t.Fatal("sync configuration must remain enabled without a user")
	}
}

func TestSelfHostedSyncWithoutCloudAccount(t *testing.T) {
	originalConf := Conf
	t.Cleanup(func() { Conf = originalConf })
	for _, provider := range []int{conf.ProviderWebDAV, conf.ProviderS3, conf.ProviderLocal} {
		Conf = NewAppConf()
		Conf.Sync = conf.NewSync()
		Conf.Sync.Provider = provider
		Conf.Sync.Enabled = true
		if !checkSync(false, false, true) {
			t.Fatalf("self-hosted provider %d requires a cloud account", provider)
		}
		if Conf.GetUser() != nil || IsSubscriber() {
			t.Fatal("self-hosted access must not fabricate a cloud subscription")
		}
		Conf.Sync.Mode = 3
		if checkSync(false, false, false) {
			t.Fatal("manual-only mode must still suppress automatic sync")
		}
		Conf.Sync.Enabled = false
		if checkSync(false, false, false) {
			t.Fatal("disabled sync must remain disabled")
		}
	}
}
